import json
import platform
import re

import plotly.io as pio
import streamlit as st

# from st_on_hover_tabs import on_hover_tabs

is_local = platform.processor() != ""


def read_from_html(filename):
    with open(str(filename)) as f:
        html = f.read()
    call_arg_str = re.findall(r"Plotly\.newPlot\((.*)\)", html)[0]
    call_args = json.loads(f"[{call_arg_str}]")
    try:
        plotly_json = {"data": call_args[1], "layout": call_args[2]}
        fig = pio.from_json(json.dumps(plotly_json))
    except Exception:
        del call_args[2]["template"]["data"]["scatter"][0]["fillpattern"]
        plotly_json = {"data": call_args[1], "layout": call_args[2]}
        fig = pio.from_json(json.dumps(plotly_json))
    return fig


MODES = {
    "DARK": ["1b9x38r", "ffhzg2", "13k62yr"],
    "CUSTOM": ["yytdko", "9swb6k", "3r9zk4", "148us62", "10hpw00"],
}

CSS = r"""
<style>

img {
    margin-bottom: 15px;
    max-width: 100%;
}
.hide {
    display: none;
}
.stAlert h4 {
    padding-top: 0px;
}
.st-ae code {
    padding: 0px !important;
}
label.effi0qh3 {
    font-size: 1.25rem;
    font-weight: 600;
    margin-top: 15px;
}
p, li {
    line-height:1.4em;
}
.st-ae h2 {
    margin-top: -15px;
}
header {
    background: rgba(255, 255, 255, 0) !important;
}
code:not(pre code) {
    color: #007bff !important;
    /* color: darkorange !important; */
}
pre code {
    white-space: pre-wrap !important;
    font-size:13px !important;
}
.st-ae code {
    padding: 4px;
}
.css-ffhzg2 .st-ae code: not(stCodeBlock) {
    background-color: black;
}
code:not(h1 code):not(h2 code):not(h3 code):not(h4 code) {
    font-size: 13px;
}
a.contents-el > code {
    color: black;
    background-color: rgb(248, 249, 251);
}
.css-fg4pbf blockquote {
    background-color: rgb(231,242,252);
    padding: 15px 20px 5px;
    border-left: 0px solid rgb(230, 234, 241);
}
.katex {
    font-size:18px;
}
h2 .katex, h3 .katex, h4 .katex {
    font-size: unset;
}
ul {
    margin-bottom: 15px;
}
ul.contents {
    line-height:1.3em; 
    list-style:none;
    color: black;
    margin-left: -15px;
}
li.margtop {
    margin-top: 12px !important;
}
ul.contents a, ul.contents a:link, ul.contents a:visited, ul.contents a:active {
    color: black;
    text-decoration: none;
}
ul.contents a:hover {
    color: black;
    text-decoration: underline;
}
details {
    margin-bottom: 10px;
    padding-left: 15px;
    padding-right: 15px;
    padding-top:5px;
    padding-bottom:1px;
    border-radius: 4px;
}
details > div.stCodeBlock {
    margin-bottom: 1rem;
}
summary {
    margin-bottom: 5px;
}
pre {
    border-radius: 0px;
}
.css-fg4pbf code {
    background: rgb(247, 248, 250);
}



details.DARK {
    background-color: #333;
}
pre.DARK:has(code.language-c) {
    background-color: #3a3a3a;
    border-radius: 0px;
}
blockquote.DARK {
    background-color: #333;
    padding: 17px 20px 1px;
}
.contents.DARK {
    color: white;
}
a.contents-el.DARK {
    color: white;
}
a.contents-el > code.DARK {
    color: orange !important;
    background-color: rgb(26, 28, 36);
}



details {
    background-color: #d1e7ff !important;
}
pre.CUSTOM:has(code.language-python) {
    border: 1px solid #abd2ff;
    border-radius: 0px;
}
pre.CUSTOM:has(code.language-c) {
    background-color: #abd2ff;
    border-radius: 0px;

    .token {
        color: black !important;
    }
}
blockquote {
    background-color: #d1e7ff;
    border-radius: 10px;
    padding: 17px 20px 1px;
}

</style>"""


def _process_match(line: str) -> str:
    """
    Converts something like "elem.CUSTOM" or ".CUSTOM.class" or ".CUSTOM:has(xyz)" into a product
    over all custom classes, which are ".st-emotion-cache-ffhzg2" etc for the different class name
    suffixes. In other words, allows us to treat "CUSTOM" as a class.
    """
    for mode in MODES:
        if mode in line:
            line_spec = line.split("{")[0]
            line_spec = ", ".join(
                [
                    line_spec.replace(mode, f"st-emotion-cache-{suffix}").strip()
                    for suffix in MODES[mode]
                ]
            )
            line = line_spec + " {"
    return line


def styling(debug=False):
    st.set_page_config(layout="wide", page_icon="🔬")
    CSS_processed = "\n".join([_process_match(line) for line in CSS.split("\n")])
    if debug:
        print(CSS_processed)
    st.markdown(CSS_processed, unsafe_allow_html=True)


def _title_to_id(title: str):
    """
    Converts a header title to an html id. This has quite a few edge cases to handle.
    """
    characters_to_delete = "()-`&?!,[]"
    characters_to_dash = "_'\"."

    for char in characters_to_delete:
        title = title.replace(char, "")
    title = title.strip()
    for char in characters_to_dash:
        title = title.replace(char, "-")

    while "  " in title:
        title = title.replace("  ", " ")
    title = title.replace(" ", "-")

    title = title.lower()
    return title


test_cases = [
    ("Extracting FVs", "extracting-fvs"),
    ("A note on `out_proj`", "a-note-on-out-proj"),
    ("Exercise - calculate fv", "exercise-calculate-fv"),
    ("Exercise (optional) - generate your own", "exercise-optional-generate-your-own"),
]
for title, id in test_cases:
    assert _title_to_id(title) == id, _title_to_id(title)


def generate_toc(markdown, debug: bool):
    """
    Takes a content string, extracts <h2> and <h3> headers from it, and creates contents page that looks like:

        ## Table of Contents

        <ul class="contents">
            <li class='margtop'><a class='contents-el' href='#extracting-fvs'>Extracting FVs</a></li>
            <li><ul class="contents">
                <li><a class='contents-el' href='#a-note-on-out-proj'>A note on <code>out_proj</code></a></li>
                <li><a class='contents-el' href='#exercise-calculate-fv'><b>Exercise</b> - calculate fv</a></li>
            </ul></li>
            <li class='margtop'><a class='contents-el' href='#multi-token-generation'>Multi-token generation</code></a></li>
            ...
        </ul>

    This will be quite a messy patchwork function.
    """
    # Remove all code blocks from the markdown
    markdown = re.sub(r"```.*?```", "", markdown, flags=re.DOTALL)

    # Regex to match h2 and h3 headers
    headers = re.findall(r"(?m)^(#+)\s*(.*)", markdown)

    # Convert headers ('##', 'Toy Model - setup') to (2, 'Toy Model - setup')
    headers = [(len(level), title) for level, title in headers if len(level) in [2, 3]]

    toc = ["## Table of Contents\n", '<ul class="contents">']
    last_level = 2

    for level, title in headers:
        # Skip some special cases
        if title.startswith("Colab"):
            continue
        if any(title.startswith(num) for num in ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "0️⃣"]):
            continue
        title = re.sub(r"\[(.*)\]\(.*\)", r"\1", title)

        # Replace backticks with <code> tags
        title_html = re.sub(r"`([^`]+)`", r"<code>\1</code>", title)

        # Bold some words at the start
        for bold_word in ["Exercise", "Bonus"]:
            title_html = re.sub(f"^{bold_word}", f"<b>{bold_word}</b>", title_html)

        if level == 2:  # h2 header
            if last_level == 3:
                toc.append("</ul></li>")
            toc.append(
                f"<li class='margtop'><a class='contents-el' href='#{_title_to_id(title)}'>"
                f"{title_html}</a></li>"
            )
            last_level = 2
        elif level == 3:  # h3 header
            if last_level == 2:
                toc.append("<li><ul class='contents'>")
            toc.append(
                f"<li><a class='contents-el' href='#{_title_to_id(title)}'>"
                f"{title_html}</a></li>"
            )
            last_level = 3

    if last_level == 3:
        toc.append("</ul></li>")

    toc.append("</ul>")

    if debug:
        print("\n".join(toc))

    return "\n".join(toc)
