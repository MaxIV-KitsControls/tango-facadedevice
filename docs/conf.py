import os
import sys
import sphinx_rtd_theme

sys.path.append(os.path.abspath("../"))
VERSION = open("../setup.py").read().split("version='")[1].split("'")[0]

project = "facadedevice"
version = VERSION
author = "Vincent Michel"
copyright = "2016, MAX-IV"

master_doc = "index"
highlight_language = "python"
extensions = ["sphinx.ext.autodoc", "sphinx.ext.napoleon"]

html_theme = "sphinx_rtd_theme"
html_theme_path = [sphinx_rtd_theme.get_html_theme_path()]

suppress_warnings = ["image.nonlocal_uri"]
