"""Remove model reasoning tags from user-visible tutor output."""


class ThoughtTokenFilter:
    START_TAGS = {"<think>", "<thinking>"}
    END_TAGS = {"</think>", "</thinking>"}
    MAX_TAG_LEN = max(len(tag) for tag in START_TAGS | END_TAGS)

    def __init__(self):
        self.in_thought = False
        self.tag_buffer = ""
        self.tag_mode = None

    def feed(self, text: str) -> str:
        output = []
        for char in (text or ""):
            if self.tag_mode:
                self.tag_buffer += char
                if char == ">":
                    tag = self.tag_buffer.lower()
                    if self.tag_mode == "normal" and tag in self.START_TAGS:
                        self.in_thought = True
                    elif self.tag_mode == "thought" and tag in self.END_TAGS:
                        self.in_thought = False
                    elif self.tag_mode == "normal":
                        output.append(self.tag_buffer)
                    self.tag_buffer = ""
                    self.tag_mode = None
                elif len(self.tag_buffer) > self.MAX_TAG_LEN:
                    if self.tag_mode == "normal":
                        output.append(self.tag_buffer)
                    self.tag_buffer = ""
                    self.tag_mode = None
                continue

            if char == "<":
                self.tag_buffer = "<"
                self.tag_mode = "thought" if self.in_thought else "normal"
            elif not self.in_thought:
                output.append(char)
        return "".join(output)

    def flush(self) -> str:
        value = self.tag_buffer if self.tag_mode == "normal" else ""
        self.tag_buffer = ""
        self.tag_mode = None
        return value


def strip_thought_content(text: str) -> str:
    filter_ = ThoughtTokenFilter()
    return filter_.feed(text) + filter_.flush()
