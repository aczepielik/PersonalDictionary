bold = lambda x: "[bold]" + x + "[/bold]"
italic = lambda x: "[italic]" + x + "[/italic]"


def main_tuple_style(tup):
    return bold(tup[0]) + ", " + italic(tup[1])


def secondary_tuples_style(tup_list):
    single_tuple = lambda tup: tup[0] + ", " + italic(tup[1])

    return "; ".join(list(map(single_tuple, tup_list)))
