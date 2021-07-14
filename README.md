## Requirements
Python 3

Installation
=================

Do NOT use `conda`, create a new environment with `venv`. Try to install from the `requirements.txt` file. 

If that does not work, follow the manual installation steps without virtual environment.


1) install [GraphViz](https://graphviz.org/download/) - the graph layouting engine on the backend

`sudo apt install graphviz`

2) Install [PyGObjects](https://pygobject.readthedocs.io/en/latest/getting_started.html#ubuntu-getting-started) - python library for GUI applications (like this one)

  - `sudo apt install libgirepository1.0-dev gcc libcairo2-dev pkg-config python3-dev gir1.2-gtk-3.0`
  - `pip3 install pycairo`
  - `pip3 install PyGObject`
  - `pip3 install pygraphviz`


Acknowledgment
====

This package was created by my student Daniel Mareda. It is based on the xdot.py library which is explained below.


About _xdot.py_
=================

_xdot.py_ is an interactive viewer for graphs written in [Graphviz](http://www.graphviz.org/)'s [dot language](http://www.graphviz.org/doc/info/lang.html).

It uses internally the GraphViz's [xdot output format](http://www.graphviz.org/doc/info/output.html#d:xdot) as an intermediate format, [Python GTK bindings](https://pygobject.readthedocs.io), and [Cairo](https://cairographics.org/) for rendering.

_xdot.py_ can be used either as a standalone application from command line, or as a library embedded in your Python application.

Requirements
============

 * [Python 3](https://www.python.org/download/)

 * [PyGObject bindings for GTK3](https://pygobject.readthedocs.io)

 * [Graphviz](http://www.graphviz.org/Download.php)

Windows users
-------------

Download and install:

 * [Python for Windows](https://www.python.org/downloads/windows/)

 * [PyGObject bindings for GTK3](https://wiki.gnome.org/action/show/Projects/PyGObject)

 * [Graphviz for Windows](http://www.graphviz.org/Download_windows.php)

Debian/Ubuntu users
-------------------

Run:

    apt-get install gir1.2-gtk-3.0 python3-gi python3-gi-cairo graphviz

Usage
=====

Command Line
------------

If you install _xdot.py_ from PyPI or from your Linux distribution package managing system, you should have the `xdot` somewhere in your `PATH` automatically.

When running _xdot.py_ from its source tree, you can run it by first setting `PYTHONPATH` environment variable to the full path of _xdot.py_'s source tree, then running:

    python3 -m xdot

You can also pass the following options:

    Usage:
    	xdot.py [file|-]
    
    Options:
      -h, --help            show this help message and exit
      -f FILTER, --filter=FILTER
                            graphviz filter: dot, neato, twopi, circo, or fdp
                            [default: dot]
      -n, --no-filter       assume input is already filtered into xdot format (use
                            e.g. dot -Txdot)
      -g GEOMETRY           default window size in form WxH
    
    Shortcuts:
      Up, Down, Left, Right     scroll
      PageUp, +, =              zoom in
      PageDown, -               zoom out
      R                         reload dot file
      F                         find
      Q                         quit
      P                         print
      Escape                    halt animation
      Ctrl-drag                 zoom in/out
      Shift-drag                zooms an area

If `-` is given as input file then _xdot.py_ will read the dot graph from the standard input.

Embedding
---------

See included `sample.py` script for an example of how to embedded _xdot.py_ into another application.

[![Screenshot](https://raw.github.com/wiki/jrfonseca/xdot.py/xdot-sample_small.png)](https://raw.github.com/wiki/jrfonseca/xdot.py/xdot-sample.png)

Download
========

  * https://pypi.python.org/pypi/xdot

  * https://github.com/jrfonseca/xdot.py

Links
=====

 * [Graphviz homepage](http://www.graphviz.org/)

 * [ZGRViewer](http://zvtm.sourceforge.net/zgrviewer.html) -- another superb graphviz/dot viewer

 * [dot2tex](https://github.com/kjellmf/dot2tex) -- python script to convert xdot output from Graphviz to a series of PSTricks or PGF/TikZ commands.

 * The [PyPy project](http://pypy.org/) also includes an [interactive dot viewer based on graphviz's plain format and the pygame library](https://morepypy.blogspot.com/2008/01/visualizing-python-tokenizer.html).
