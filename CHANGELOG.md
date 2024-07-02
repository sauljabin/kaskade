# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Lag is the result of a sum instead of a max
- Upgrade textual library

## [2.1.0] - 2024-06-30

### Added

- New edit topic screen
- Enforce to type topic's name when deleting
- Modify the chunk size on the consumer
- Consumer filters
- Remove schema registry magic bytes on json deserializer
- Add support for native deserialization: boolean, floata dn long

### Changed

- Improve consumer performance

### Fixed

- Using the right retention config name
- Duplicated headers were hidden. Now it shows duplicated headers

## [2.0.1] - 2024-06-27

### Fixed

- Documentation and help

## [2.0.0] - 2024-06-27

### Added

- Update scripts
- Add chageloggh
- New arguments
- Topic filter
- Json deserialization
- Create and delete topic

### Changed

- New styles
- textual and confluent-kafka upgraded
- Command admin and consumer

### Removed

- Unit test, confluent-kafka and textual are changing a lot
- Schema registry

## [1.1.8] - 2022-07-26

### Fixed

- Fix scrolling

## [1.1.7] - 2022-07-25

### Fixed

- Error when looking for config files

## [1.1.6] - 2022-07-25

### Fixed

- Unpack schema id error

## [1.1.5] - 2022-07-25

### Fixed

- Schema registry error accessing internal object

## [1.1.4] - 2022-07-25

### Fixed

- Close session error when None

## [1.1.3] - 2022-07-25

### Fixed

- Unicode error
- Close socket error when calling schema registry

## [1.1.2] - 2022-07-24

### Fixed

- Error when consuming key and value None

## [1.1.1] - 2022-07-24

### Fixed

- Remove an unused setting

## [1.1.0] - 2022-07-24

### Added

- Show/Hide internal topics

### Fixed

- Error when kafka has empty groups

## [1.0.0] - 2022-07-24

### Add

- Schema registry support

[Unreleased]: https://github.com/sauljabin/kaskade/compare/v2.1.0...HEAD
[2.1.0]: https://github.com/sauljabin/kaskade/compare/v2.0.1...v2.1.0
[2.0.1]: https://github.com/sauljabin/kaskade/compare/v2.0.0...v2.0.1
[2.0.0]: https://github.com/sauljabin/kaskade/compare/v1.1.8...v2.0.0
[1.1.8]: https://github.com/sauljabin/kaskade/compare/v1.1.7...v1.1.8
[1.1.7]: https://github.com/sauljabin/kaskade/compare/v1.1.6...v1.1.7
[1.1.6]: https://github.com/sauljabin/kaskade/compare/v1.1.5...v1.1.6
[1.1.5]: https://github.com/sauljabin/kaskade/compare/v1.1.4...v1.1.5
[1.1.4]: https://github.com/sauljabin/kaskade/compare/v1.1.3...v1.1.4
[1.1.3]: https://github.com/sauljabin/kaskade/compare/v1.1.2...v1.1.3
[1.1.2]: https://github.com/sauljabin/kaskade/compare/v1.1.1...v1.1.2
[1.1.1]: https://github.com/sauljabin/kaskade/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/sauljabin/kaskade/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/sauljabin/kaskade/releases/tag/v1.0.0