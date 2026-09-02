from __future__ import annotations

import ssl
import tempfile
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote

import httpx

APICURIO_PREFIX = "apicurio.registry."
APICURIO_URL = f"{APICURIO_PREFIX}url"
APICURIO_USE_ID = f"{APICURIO_PREFIX}use-id"
APICURIO_CHECK_PERIOD = f"{APICURIO_PREFIX}check-period-ms"
APICURIO_RETRY_COUNT = f"{APICURIO_PREFIX}retry-count"
APICURIO_RETRY_BACKOFF = f"{APICURIO_PREFIX}retry-backoff-ms"
APICURIO_TOKEN_ENDPOINT = f"{APICURIO_PREFIX}auth.service.token.endpoint"
APICURIO_CLIENT_ID = f"{APICURIO_PREFIX}auth.client.id"
APICURIO_CLIENT_SECRET = f"{APICURIO_PREFIX}auth.client.secret"
APICURIO_USERNAME = f"{APICURIO_PREFIX}auth.username"
APICURIO_PASSWORD = f"{APICURIO_PREFIX}auth.password"
APICURIO_PROXY_HOST = f"{APICURIO_PREFIX}proxy.host"
APICURIO_PROXY_PORT = f"{APICURIO_PREFIX}proxy.port"
APICURIO_PROXY_USERNAME = f"{APICURIO_PREFIX}proxy.username"
APICURIO_PROXY_PASSWORD = f"{APICURIO_PREFIX}proxy.password"
APICURIO_TLS_CERTIFICATES = f"{APICURIO_PREFIX}tls.certificates"
APICURIO_TLS_TRUST_ALL = f"{APICURIO_PREFIX}tls.trust-all"
APICURIO_TLS_VERIFY_HOST = f"{APICURIO_PREFIX}tls.verify-host"
APICURIO_TLS_CLIENT_CERTIFICATE = f"{APICURIO_PREFIX}tls.client-certificate"
APICURIO_TLS_CLIENT_KEY = f"{APICURIO_PREFIX}tls.client-key"
APICURIO_CACHE_CAPACITY = 1000

APICURIO_PROPERTIES = {
    APICURIO_URL,
    APICURIO_USE_ID,
    APICURIO_CHECK_PERIOD,
    APICURIO_RETRY_COUNT,
    APICURIO_RETRY_BACKOFF,
    APICURIO_TOKEN_ENDPOINT,
    APICURIO_CLIENT_ID,
    APICURIO_CLIENT_SECRET,
    APICURIO_USERNAME,
    APICURIO_PASSWORD,
    APICURIO_PROXY_HOST,
    APICURIO_PROXY_PORT,
    APICURIO_PROXY_USERNAME,
    APICURIO_PROXY_PASSWORD,
    APICURIO_TLS_CERTIFICATES,
    APICURIO_TLS_TRUST_ALL,
    APICURIO_TLS_VERIFY_HOST,
    APICURIO_TLS_CLIENT_CERTIFICATE,
    APICURIO_TLS_CLIENT_KEY,
}


class ApicurioRegistryError(ValueError):
    """Raised for native Apicurio configuration and HTTP failures."""


def _integer(config: dict[str, str], name: str, default: int) -> int:
    value = config.get(name)
    if value is None:
        return default
    try:
        result = int(value)
    except ValueError as ex:
        raise ApicurioRegistryError(f"{name} must be an integer") from ex
    if result < 0:
        raise ApicurioRegistryError(f"{name} must be zero or greater")
    return result


def _boolean(config: dict[str, str], name: str, default: bool) -> bool:
    value = config.get(name)
    if value is None:
        return default
    normalized = value.lower()
    if normalized not in {"true", "false"}:
        raise ApicurioRegistryError(f"{name} must be true or false")
    return normalized == "true"


def _complete_set(config: dict[str, str], names: set[str], label: str) -> bool:
    supplied = names.intersection(config)
    missing_names = {name for name in names if not config.get(name)}
    if supplied and missing_names:
        missing = ", ".join(sorted(missing_names))
        raise ApicurioRegistryError(f"Incomplete {label} configuration; missing: {missing}")
    return bool(supplied)


@dataclass(frozen=True)
class ApicurioConfig:
    url: str
    use_id: str
    check_period_ms: int
    retry_count: int
    retry_backoff_ms: int
    username: str | None
    password: str | None
    token_endpoint: str | None
    client_id: str | None
    client_secret: str | None
    proxy: str | None
    verify: bool | ssl.SSLContext
    certificate: tuple[str, str] | None

    @classmethod
    def from_dict(cls, config: dict[str, str]) -> ApicurioConfig:  # noqa: C901
        unknown = sorted(set(config) - APICURIO_PROPERTIES - {"provider"})
        unsupported_stores = [
            name
            for name in config
            if name.startswith(
                (
                    f"{APICURIO_PREFIX}tls.keystore.",
                    f"{APICURIO_PREFIX}tls.truststore.",
                )
            )
        ]
        if unsupported_stores:
            raise ApicurioRegistryError(
                "JKS and PKCS12 stores are not supported; use the Apicurio PEM TLS properties"
            )
        if unknown:
            raise ApicurioRegistryError(f"Unrecognized Apicurio properties: {', '.join(unknown)}")

        url = config.get(APICURIO_URL, "").rstrip("/")
        if not url:
            raise ApicurioRegistryError(f"Missing required configuration property {APICURIO_URL}")
        parsed_url = httpx.URL(url)
        if parsed_url.scheme not in {"http", "https"} or parsed_url.host is None:
            raise ApicurioRegistryError(f"Invalid url {url}")

        use_id_value = config.get(APICURIO_USE_ID, "contentId")
        use_id_lookup = {"contentid": "contentId", "globalid": "globalId"}
        use_id = use_id_lookup.get(use_id_value.lower())
        if use_id is None:
            raise ApicurioRegistryError(f"{APICURIO_USE_ID} must be contentId or globalId")

        basic_names = {APICURIO_USERNAME, APICURIO_PASSWORD}
        oauth_names = {APICURIO_TOKEN_ENDPOINT, APICURIO_CLIENT_ID, APICURIO_CLIENT_SECRET}
        has_basic = _complete_set(config, basic_names, "Basic authentication")
        has_oauth = _complete_set(config, oauth_names, "OAuth client credentials")
        if has_basic and has_oauth:
            raise ApicurioRegistryError(
                "Basic authentication and OAuth cannot be configured together"
            )

        proxy_names = {APICURIO_PROXY_HOST, APICURIO_PROXY_PORT}
        has_proxy = _complete_set(config, proxy_names, "proxy")
        proxy_username = config.get(APICURIO_PROXY_USERNAME)
        proxy_password = config.get(APICURIO_PROXY_PASSWORD)
        if bool(proxy_username) != bool(proxy_password):
            raise ApicurioRegistryError("Proxy username and password must be configured together")
        if (proxy_username or proxy_password) and not has_proxy:
            raise ApicurioRegistryError("Proxy credentials require proxy host and port")
        proxy = None
        if has_proxy:
            try:
                proxy_port = int(config[APICURIO_PROXY_PORT])
            except ValueError as ex:
                raise ApicurioRegistryError(f"{APICURIO_PROXY_PORT} must be an integer") from ex
            if not 1 <= proxy_port <= 65535:
                raise ApicurioRegistryError(f"{APICURIO_PROXY_PORT} must be between 1 and 65535")
            credentials = ""
            if proxy_username is not None and proxy_password is not None:
                credentials = f"{quote(proxy_username, safe='')}:{quote(proxy_password, safe='')}@"
            proxy = f"http://{credentials}{config[APICURIO_PROXY_HOST]}:{proxy_port}"

        trust_all = _boolean(config, APICURIO_TLS_TRUST_ALL, False)
        verify_host = _boolean(config, APICURIO_TLS_VERIFY_HOST, True)
        certificates = config.get(APICURIO_TLS_CERTIFICATES)
        verify: bool | ssl.SSLContext = not trust_all
        if not trust_all and (certificates or not verify_host):
            try:
                context = ssl.create_default_context()
                if certificates:
                    if "-----BEGIN CERTIFICATE-----" in certificates:
                        context.load_verify_locations(
                            cadata=certificates.replace(",-----", "\n-----")
                        )
                    else:
                        for certificate_path in certificates.split(","):
                            context.load_verify_locations(cafile=certificate_path.strip())
            except OSError as ex:
                raise ApicurioRegistryError(f"TLS certificate file is invalid: {ex}") from ex
            context.check_hostname = verify_host
            verify = context

        client_certificate = config.get(APICURIO_TLS_CLIENT_CERTIFICATE)
        client_key = config.get(APICURIO_TLS_CLIENT_KEY)
        if bool(client_certificate) != bool(client_key):
            raise ApicurioRegistryError(
                "TLS client certificate and client key must be configured together"
            )
        certificate = None
        if client_certificate is not None and client_key is not None:
            certificate = (client_certificate, client_key)

        return cls(
            url=url,
            use_id=use_id,
            check_period_ms=_integer(config, APICURIO_CHECK_PERIOD, 30000),
            retry_count=_integer(config, APICURIO_RETRY_COUNT, 3),
            retry_backoff_ms=_integer(config, APICURIO_RETRY_BACKOFF, 300),
            username=config.get(APICURIO_USERNAME),
            password=config.get(APICURIO_PASSWORD),
            token_endpoint=config.get(APICURIO_TOKEN_ENDPOINT),
            client_id=config.get(APICURIO_CLIENT_ID),
            client_secret=config.get(APICURIO_CLIENT_SECRET),
            proxy=proxy,
            verify=verify,
            certificate=certificate,
        )


@dataclass(frozen=True)
class ApicurioReference:
    name: str
    group: str
    artifact: str
    version: str


@dataclass(frozen=True)
class ApicurioArtifact:
    id: int
    id_kind: str
    content: str
    type: str
    references: tuple[ApicurioReference, ...]


class ApicurioClient:
    """Small synchronous client for the Apicurio Registry Core API v3."""

    CACHE_CAPACITY = APICURIO_CACHE_CAPACITY

    def __init__(self, config: dict[str, str]):
        self.config = ApicurioConfig.from_dict(config)
        self._certificate_directory: tempfile.TemporaryDirectory[str] | None = None
        auth = None
        if self.config.username is not None and self.config.password is not None:
            auth = (self.config.username, self.config.password)
        try:
            self.http = httpx.Client(
                base_url=self.config.url,
                auth=auth,
                proxy=self.config.proxy,
                verify=self.config.verify,
                cert=self._certificate_files(self.config.certificate),
            )
        except (OSError, ValueError) as ex:
            raise ApicurioRegistryError(f"Unable to configure Apicurio HTTP client: {ex}") from ex
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._cache: OrderedDict[tuple[Any, ...], tuple[float, Any]] = OrderedDict()

    def _certificate_files(self, certificate: tuple[str, str] | None) -> tuple[str, str] | None:
        if certificate is None:
            return None
        if all(Path(value).is_file() for value in certificate):
            return certificate
        if not all("-----BEGIN" in value for value in certificate):
            missing = next(value for value in certificate if not Path(value).is_file())
            raise ApicurioRegistryError(f"TLS PEM file not found: {missing}")
        self._certificate_directory = tempfile.TemporaryDirectory()
        directory = Path(self._certificate_directory.name)
        certificate_path = directory / "client.pem"
        key_path = directory / "client.key"
        certificate_path.write_text(certificate[0], encoding="utf-8")
        key_path.write_text(certificate[1], encoding="utf-8")
        return str(certificate_path), str(key_path)

    def _cached(self, key: tuple[Any, ...]) -> Any | None:
        item = self._cache.get(key)
        if item is None:
            return None
        created_at, value = item
        if (
            self.config.check_period_ms == 0
            or (time.monotonic() - created_at) * 1000 >= self.config.check_period_ms
        ):
            del self._cache[key]
            return None
        self._cache.move_to_end(key)
        return value

    def _store(self, key: tuple[Any, ...], value: Any) -> None:
        self._cache[key] = (time.monotonic(), value)
        self._cache.move_to_end(key)
        while len(self._cache) > self.CACHE_CAPACITY:
            self._cache.popitem(last=False)

    def _oauth_token(self, force: bool = False) -> str | None:
        if self.config.token_endpoint is None:
            return None
        now = time.monotonic()
        if not force and self._token is not None and now < self._token_expires_at:
            return self._token
        assert self.config.client_id is not None
        assert self.config.client_secret is not None
        try:
            response = self.http.post(
                self.config.token_endpoint,
                data={"grant_type": "client_credentials"},
                auth=(self.config.client_id, self.config.client_secret),
            )
            response.raise_for_status()
            body = response.json()
            token = body["access_token"]
            expires_in = max(0, int(body.get("expires_in", 60)))
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as ex:
            raise ApicurioRegistryError(f"OAuth token request failed: {ex}") from ex
        self._token = str(token)
        self._token_expires_at = now + max(0, expires_in - min(30, expires_in / 10))
        return self._token

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        configured_headers = dict(kwargs.pop("headers", {}))
        refreshed = False
        attempts = self.config.retry_count + 1
        attempt = 0
        while attempt < attempts:
            headers = dict(configured_headers)
            token = self._oauth_token()
            if token is not None:
                headers["Authorization"] = f"Bearer {token}"
            try:
                response = self.http.request(method, path, headers=headers, **kwargs)
                if response.status_code == 401 and token is not None and not refreshed:
                    refreshed = True
                    self._token = None
                    self._oauth_token(force=True)
                    continue
                if response.status_code == 429 or response.status_code >= 500:
                    attempt += 1
                    if attempt < attempts:
                        time.sleep(self.config.retry_backoff_ms / 1000)
                        continue
                response.raise_for_status()
                return response
            except httpx.HTTPError as ex:
                attempt += 1
                if attempt >= attempts:
                    raise ApicurioRegistryError(f"Apicurio request failed: {ex}") from ex
                time.sleep(self.config.retry_backoff_ms / 1000)
        raise ApicurioRegistryError("Apicurio request failed")

    def get_artifact(self, artifact_id: int) -> ApicurioArtifact:
        cache_key = ("artifact", self.config.use_id, artifact_id)
        cached = self._cached(cache_key)
        if cached is not None:
            return cast(ApicurioArtifact, cached)
        id_path = "contentIds" if self.config.use_id == "contentId" else "globalIds"
        response = self._request(
            "GET",
            f"/ids/{id_path}/{artifact_id}",
            params={"returnArtifactType": "true"},
        )
        artifact_type = response.headers.get("X-Registry-ArtifactType", "").upper()
        if not artifact_type:
            content_type = response.headers.get("Content-Type", "")
            for parameter in content_type.split(";")[1:]:
                name, separator, value = parameter.strip().partition("=")
                if separator and name.lower() == "artifacttype":
                    artifact_type = value.strip('"').upper()
                    break
        if not artifact_type:
            metadata_types = {
                str(value.get("artifactType", "")).upper()
                for value in self.get_metadata(artifact_id)
                if value.get("artifactType")
            }
            if len(metadata_types) == 1:
                artifact_type = metadata_types.pop()
        if artifact_type not in {"AVRO", "JSON", "PROTOBUF"}:
            raise ApicurioRegistryError(
                f"Unsupported or missing Apicurio artifact type: {artifact_type or 'unknown'}"
            )
        references = self._references(f"/ids/{id_path}/{artifact_id}/references")
        result = ApicurioArtifact(
            id=artifact_id,
            id_kind="CONTENT_ID" if self.config.use_id == "contentId" else "GLOBAL_ID",
            content=response.text,
            type=artifact_type,
            references=references,
        )
        self._store(cache_key, result)
        return result

    def get_referenced_artifact(
        self, reference: ApicurioReference, artifact_type: str
    ) -> ApicurioArtifact:
        key = ("reference", reference.group, reference.artifact, reference.version)
        cached = self._cached(key)
        if cached is not None:
            return cast(ApicurioArtifact, cached)
        group = quote(reference.group, safe="")
        artifact = quote(reference.artifact, safe="")
        version = quote(reference.version, safe="")
        base = f"/groups/{group}/artifacts/{artifact}/versions/{version}"
        response = self._request("GET", f"{base}/content")
        references = self._references(f"{base}/references")
        result = ApicurioArtifact(0, "REFERENCE", response.text, artifact_type, references)
        self._store(key, result)
        return result

    def _references(self, path: str) -> tuple[ApicurioReference, ...]:
        response = self._request("GET", path)
        try:
            values = response.json()
            return tuple(
                ApicurioReference(
                    name=value["name"],
                    group=value.get("groupId", "default"),
                    artifact=value["artifactId"],
                    version=str(value["version"]),
                )
                for value in values
            )
        except (KeyError, TypeError, ValueError) as ex:
            raise ApicurioRegistryError("Invalid Apicurio references response") from ex

    def get_metadata(self, artifact_id: int) -> list[dict[str, Any]]:
        cache_key = ("metadata", self.config.use_id, artifact_id)
        cached = self._cached(cache_key)
        if cached is not None:
            return cast(list[dict[str, Any]], cached)
        parameter = self.config.use_id
        values: list[dict[str, Any]] = []
        offset = 0
        limit = 100
        while True:
            response = self._request(
                "GET",
                "/search/versions",
                params={parameter: artifact_id, "limit": limit, "offset": offset},
            )
            try:
                body = response.json()
                page = body.get("artifacts", body.get("versions", []))
                count = int(body.get("count", len(page)))
                if not isinstance(page, list):
                    raise TypeError
            except (TypeError, ValueError) as ex:
                raise ApicurioRegistryError("Invalid Apicurio version search response") from ex
            values.extend(page)
            offset += len(page)
            if not page or offset >= count or len(page) < limit:
                break
        self._store(cache_key, values)
        return values
