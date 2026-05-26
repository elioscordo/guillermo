from audiostretchy.stretch import stretch_audio


def get_name(algo, payload):
    """
    User to tag the audio with the name of the algo
    """
    tokens = [algo]
    for x, y in payload.items():
        tokens.append(x)
        tokens.append(str(y))
    return "-".join(tokens)


def resize(input_file, output_file, ratio=1):
    stretch_audio(input_file, output_file, ratio=ratio)
