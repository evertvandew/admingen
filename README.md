# Administrative Application Generator

This repository is an active research project into the generation of administrative applications.

Administrative applications generally consist of a database and a web interface for modifying this database.
A large part of this web interface can be generated from knowledge of the database, but some
custom widgets and/or database queries are usually required.

This project contains a varied set of tools and utilities. Examples are:

* A file-based database that is useful for testing and debugging. This database currently has a custom API, in future it will also support an SQL frontend. Obviously this is not to be used for production.
* Tools for using CSV files as an in-memory database.
* Three different methods for creating a web interface.
    - A server-side on-the-fly HTML generation framework
    - An extensible XML-based specification language from which static HTML is generated
      This static HTML uses Javascript for handling dynamic content.
      The language also handles downloading and updating components, creating the database model, the server etc.
    - An object-based generation framework for generating HTML, either statically or server-side.
      This HTML also uses Javascript for handling dynamic content.

# Installation

Install the code using the following commands:

    pip install git+https://github.com/evertvandew/admingen

# Usage

The project contains a number of example projects that use the various features of the package.
These examples have their own README.md files explaining how they work.
