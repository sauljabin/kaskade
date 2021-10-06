class CircularList:
    def __init__(self, wrapped):
        self.list = wrapped
        self.index = -1

    def __next__(self):
        return self.next()

    def __len__(self):
        return len(self.list)

    def next(self):
        self.index += 1
        if self.index >= len(self.list):
            self.index = 0
        return self.list[self.index]

    def previous(self):
        self.index -= 1
        if self.index < 0:
            self.index = len(self.list) - 1
        return self.list[self.index]
