# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information
from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

sys.path.insert(0, str(Path("..").resolve()))

import gusnet

if TYPE_CHECKING:
    from gusnet.elements import (
        Field,
        FieldType,
    )

project = "Gusnet - Piped Water Network Analysis"
project_copyright = "2024, Angus McBride"
author = "Angus McBride"
release = gusnet.__version__

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "myst_parser",
    "sphinx.ext.intersphinx",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "enum_tools.autoenum",
    "sphinx_autodoc_typehints",
    "sphinxcontrib.googleanalytics",
    "sphinx_design",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "pydata_sphinx_theme"
html_static_path = ["_static"]
html_logo = "../gusnet/resources/icons/logo.svg"
html_favicon = html_logo

html_theme_options = {
    "logo": {"text": "Gusnet"},
    "secondary_sidebar_items": [],
    "icon_links": [
        {
            # Label for this link
            "name": "GitHub",
            # URL where the link will redirect
            "url": "https://github.com/angusmcb/gusnet",  # required
            # Icon class (if "type": "fontawesome"), or path to local image (if "type": "local")
            "icon": "fa-brands fa-github",
            # The type of image to be used (see below for details)
            "type": "fontawesome",
        },
        {
            # Label for this link
            "name": "QGIS Plugin Page",
            # URL where the link will redirect
            "url": "https://plugins.qgis.org/plugins/gusnet/",  # required
            # Icon class (if "type": "fontawesome"), or path to local image (if "type": "local")
            "icon": "_static/QGIS_logo_minimal.svg",
            # The type of image to be used (see below for details)
            "type": "local",
        },
        {
            # Label for this link
            "name": "WNTR documentation",
            # URL where the link will redirect
            "url": "https://usepa.github.io/WNTR/",  # required
            # Icon class (if "type": "fontawesome"), or path to local image (if "type": "local")
            "icon": "_static/water_circle.png",
            # The type of image to be used (see below for details)
            "type": "local",
        },
    ],
}


intersphinx_mapping = {
    "qgis": ("https://qgis.org/pyqgis/master/", None),
    "wntr": ("https://usepa.github.io/WNTR/", None),
    "python": ("https://docs.python.org/3", None),
    "pandas": ("https://pandas.pydata.org/docs/", None),
    "numpy": ("https://numpy.org/doc/stable/", None),
    "qgisdocs": ("https://docs.qgis.org/latest/en/", None),
    "epanet": ("https://epanet22.readthedocs.io/en/latest/", None),
}
myst_url_schemes = [
    "http",
    "https",
]

myst_enable_extensions = ["colon_fence", "attrs_block", "attrs_inline"]

numfig = True
numfig_format = {"figure": "Figure %s", "table": "Table %s", "code-block": "Listing %s"}


autodoc_type_aliases = {"Iterable": "Iterable", "ArrayLike": "ArrayLike"}
# add_module_names = False
autodoc_member_order = "bysource"

googleanalytics_id = "G-EXG3JYMMHK"


def generate_attributes_table(_):
    from gusnet.elements import FieldGroup, ModelLayer

    output_dir = Path(__file__).parent / "_build" / "autogen-includes"
    output_dir.mkdir(parents=True, exist_ok=True)
    for layer in ModelLayer:
        table = pd.DataFrame(
            [
                (
                    field.value + ("*" if field.field_group & FieldGroup.REQUIRED else ""),
                    field.friendly_name,
                    field_type_str(field.type),
                    field_value(field),
                    field_analysis_type(field),
                )
                for field in layer.wq_fields()
            ],
            columns=["Attribute", "Alias", "Type", "Value(s)", "Used for"],
        )
        table.to_csv(output_dir / (layer.name.lower() + ".csv"), index=False)


def field_type_str(field_type: FieldType) -> str:
    from gusnet.elements import MapFieldType, Parameter, SimpleFieldType

    if field_type is SimpleFieldType.PATTERN:
        return "Text (string) *or* Decimal list"
    if field_type in [SimpleFieldType.CURVE, SimpleFieldType.STR] or field_type in MapFieldType:
        return "Text (string)"
    if isinstance(field_type, Parameter):
        return "Decimal (double)"
    if field_type is SimpleFieldType.BOOL:
        return "Boolean"

    raise KeyError(field_type)


def field_value(field: Field) -> str:
    from gusnet.elements import Field, MapFieldType, SimpleFieldType

    if isinstance(field.type, MapFieldType):
        return ", ".join(["`" + enum.value + "`" for enum in field.type.value])
    if field.type is SimpleFieldType.PATTERN:
        return "Pattern"
    if field.type is SimpleFieldType.CURVE:
        return "Curve"
    if field is Field.NAME:
        return "Will generate automatically if blank"
    if field is Field.LENGTH:
        return "Will calculate if blank"

    return ""


def field_analysis_type(field: Field) -> str:
    from gusnet.elements import FieldGroup

    analysis_types_of_interest = [
        FieldGroup.PRESSURE_DEPENDENT_DEMAND,
        FieldGroup.ENERGY,
        FieldGroup.WATER_QUALITY_ANALYSIS,
    ]
    return ", ".join(
        [str(g.name).title().replace("_", " ") for g in analysis_types_of_interest if g in field.field_group]
    )


def setup(app):
    app.connect("builder-inited", generate_attributes_table)
