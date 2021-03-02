
# Using `Admingen`


`Admingen` is a collection of tools useful for creating administrative software. 
At the moment it is a bit of a hodge-podge, perhaps in future it will be
restructured into more single-purpose libraries.

# Overview
`Admingen` is split in a number of groups:

* A templating system in XML. This makes it easy to use XML to define parts of an application.
* A number of specific tools to transform XML definitions into HTML pages or a data model.
* Functions to handle data. This includes serializing and deserializing data, and defining data.
* A framework for deploying applications, using simple yet powerful mechanisms to configure them.
* Standard clients for e.g. email and common services defined by third parties.
* Tools to simplify testing of applications.

A number of nuggets are defined:

* A simple key-ring that allows a single application a place to store sensitive information safely.
* A file-based database that is easier to use when developing and testing an application
  then real (SQL) databases. `Admingen` uses an interface to make it easy to switch between the file-based
  database and relational databases.
* A simple modular server, based on `Flask`, to serve HTML and data. It can be extended with access control and database modules
  as required by the application.

# Creating an `admingen` application
For now, `admingen` is used as a git submodule. The `src` directory should be put in the `PYTHONPATH`, and the tools
are located in the `bin` directory. When mature, it can be installed as a regular Python module.

