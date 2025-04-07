def ftStr(word: str, emphasis_index: int = 0) -> str:
    '''
    Helper function to format a string with bold and underline formatting.
    '''
    word = word.strip()
    if word == "":
        return ""
    opt = "\033[1m" + word[:emphasis_index] + "\033[0m"
    if emphasis_index < len(word):
        opt += "\033[1;4m" + word[emphasis_index] + "\033[0m"
    if emphasis_index + 1 < len(word):
        opt += "\033[1m" + word[emphasis_index + 1:] + "\033[0m"
    return opt
