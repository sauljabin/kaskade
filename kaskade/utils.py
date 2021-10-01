class CircularList:
    def __init__(self, original_list):
        self.__list = original_list
        self.__index = -1

    def __iter__(self):
        return self

    def __next__(self):
        return self.next()

    def __len__(self):
        return len(self.__list)

    def next(self):
        self.__index += 1
        if self.__index >= len(self.__list):
            self.__index = 0
        return self.__list[self.__index]

    def previous(self):
        self.__index -= 1
        if self.__index < 0:
            self.__index = len(self.__list) - 1
        return self.__list[self.__index]
