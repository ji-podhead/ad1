# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'ad1 Platform'
copyright = '2025, ad1 Team'
author = 'ad1 Team'
release = '0.1.0'

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
import os
import sys
sys.path.insert(0, os.path.abspath('../../../')) # Changed to project root


# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.autodoc',      # Include documentation from docstrings
    'sphinx.ext.napoleon',     # Support for Google and NumPy style docstrings
    'sphinx_autodoc_typehints', # Integrate type hints into the documentation
    'sphinx.ext.viewcode',     # Add links to source code
    'sphinx.ext.intersphinx',  # Link to other projects' documentation
    'm2r2',                    # For including Markdown files
    'sphinx_rtd_theme',        # Read the Docs theme
]

templates_path = ['_templates']
exclude_patterns = []


# Add m2r2 source suffix for Markdown files
source_suffix = ['.rst', '.md']


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']
autosummary_generate = True  # Turn on sphinx.ext.autosummary

# Add any paths that contain templates here, relative to this directory.
# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information
# html_theme = 'alabaster'
# html_static_path = ['_static']

html_theme = 'sphinx_rtd_theme'
html_theme_options = {
    "rightsidebar": "true",
    "relbarbgcolor": "black"
}