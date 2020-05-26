## makefile.py ##

Automatically generate a Makefile for a C/C++ codebase.
Includes support for [protobuf](https://developers.google.com/protocol-buffers) files,
[gRPC](https://grpc.io/) service definitions, and [CCH](https://github.com/tjps/cch) files.

makefile.py is designed to be run each time you would run `make`.
It determines all relevant source files, parses them to recreate the
dependency graph, and outputs a Makefile that can then be run normally with `make`.

One goal of this project is to have minimal dependencies:

  * GNU Make
  * Python 3.x

Pull requests are welcome.  Some ideas:

  * making the preamble more general
  * support alternative output targets - [Jamfiles](https://www.boost.org/doc/libs/1_33_1/doc/html/bbv2/advanced/jamfiles.html), [Ninja](https://ninja-build.org/), [doit](https://pydoit.org/), etc.
