.. verse documentation master file, created by
   sphinx-quickstart on Fri Jul 29 22:19:35 2022.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to verse's documentation!
=================================

Verse is a Python library for creating, simulating, and verifying scenarios with interacting, decision making agents. The decision logic can be written in an expressive subset of Python. The continuous evolution can be described as a black-box simulation function. The agent can be ported across different maps, which can be defined from scratch or imported from opendrive files. Verse scenarios can be simulated and verified using hybrid reachability analysis.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   getting_started.rst
   agent.rst
   map.rst
   sensor.rst
   scenario.rst
   parser.md
   outputs.rst
   plotting.rst
   contributors.rst


API Documentation
~~~~~~~~~~~~~~~~~
.. autosummary::
   :toctree: _autosummary
   :template: custom-module-template.rst
   :recursive:

   verse

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
