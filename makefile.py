#!/usr/bin/env python3
# -- https://github.com/tjps/makefile.py --
# This script is an automatic Makefile generator for C/C++ codebases.
#
# It finds all buildable object file sources (e.g. .cch, .cc, ...)
# and generates a build command for each one based on the
# list of #include's it contains.
#
# For each .cc that contains "int main(...)" a link step is generated.
#
# The end result is a Makefile that has a build target for each executable
# with all of the compile time and link time dependencies in place.
#
# There are additional nuances, such as special comments that can inject
# compile or link time flags, and debug output to check the dependency
# graph for cycles.  TODO: this last piece is no longer true.
#
# Compile/link arguments for an object can be specified
# with the special comment forms:
#
#     // @compileargs -Ithird-party/libfoo/include/ (etc.)
#     // @linkargs -lz (etc.)
#


import os
import re
import sys
import pathlib
import argparse
from enum import Enum
from textwrap import dedent
from collections import defaultdict
from os.path import join as pathjoin


file_types = {}
def handles(extension, produces=None):
    """ Class decorator that registers a class
        as handling a specific file extension. """
    def deco(cls):
        file_types[extension] = cls
        setattr(cls, "extension", extension)
        setattr(cls, "produces", produces or [])
        return cls
    return deco


# These regex helpers remain at global scope so that the
# compiled regex caching is done once per process.
def has_main(contents, regex=re.compile(r'^\s*int\s+main\s*\((int[^\)]*|\s*)\)', re.MULTILINE)):
    return regex.search(contents) != None
def get_includes(contents, regex=re.compile(r'^\s*#include\s*"([^"]+)"\s*$', re.MULTILINE)):
    return regex.findall(contents)
def get_imports(contents, regex=re.compile(r'^\s*import\s*"([^"]+)"\s*;\s*$', re.MULTILINE)):
    return regex.findall(contents)
def get_compileargs(contents, regex=re.compile(r'^\s*//\s*@compileargs\s+(.*)\s*$', re.MULTILINE)):
    return regex.findall(contents)
def get_linkargs(contents, regex=re.compile(r'^\s*//\s*@linkargs\s+(.*)\s*$', re.MULTILINE)):
    return regex.findall(contents)



class Emitted:
    """ Struct returned by emit() describing emitted artifacts. """
    def __init__(self, directories=None, executables=None, patterns=None):
        self.directories = directories
        self.executables = executables
        self.patterns = patterns

class FileAction(Enum):
    INCOMPATIBLE = 1
    REPLACE = 2
    DROP = 3


class File:

    def __init__(self, filename, contents):
        self.fullpath = filename
        assert filename.startswith(src_dir)
        self.filename = filename[len(src_dir):]
        self.dirname = os.path.dirname(self.filename)
        (self.base, self.extension) = os.path.splitext(self.filename)
        self.dependencies = []
        self.includes = []
        self.compileargs = []
        self.linkargs = []
        self.initialize(contents)

    def initialize(self, contents):
        assert False, "Not implemented in base class"

    def swap_extension(self, new_extension):
        return self.base + new_extension

    def get_variants(self, extensions, prepend_dir=""):
        return [pathjoin(prepend_dir, self.swap_extension(e)) for e in extensions]

    def get_aliases(self):
        return [self.filename]

    def artifacts(self):
        return self.get_variants(self.produces)

    def emit(self, out_dir):
        return Emitted()  # By default emit nothing.

    def has_relation(self, file):
        return FileAction.INCOMPATIBLE

    def __recursive_deps(self, deps=None, seen=None):
        # TODO: memoize?
        if not seen:
            seen = set()
        if not deps:
            deps = []
        for dep in self.dependencies:
            if not dep.filename in seen:
                seen.add(dep.filename)
                deps.append(dep)
                dep.__recursive_deps(deps, seen)
        return deps

    def __apply_rec(self, getter):
        ret = []
        for dep in self.__recursive_deps():
            ret += getter(dep)
        return ret

    def get_compile_dependencies(self):
        return self.__apply_rec(lambda dep: dep.get_aliases()[-1:])

    def get_link_dependencies(self):
        return self.__apply_rec(lambda dep: dep.artifacts())

    def get_linkargs(self):
        return set(self.__apply_rec(lambda dep: dep.linkargs))

    def __str__(self):
        return f"{self.filename}"


@handles(extension=".cc", produces=[".o"])
class CCFile(File):

    def initialize(self, contents):
        self.includes = get_includes(contents)
        self.compileargs = get_compileargs(contents)
        self.linkargs = get_linkargs(contents)
        self.__is_link_target = has_main(contents)

    def get_aliases(self):
        return [self.filename, self.swap_extension(".h")]

    def has_relation(self, file):
        if self.swap_extension(".h") == file.filename:
            return FileAction.DROP
        return FileAction.INCOMPATIBLE

    def emit(self, out_dir):
        obj_file = pathjoin(out_dir, self.swap_extension(".o"))
        includes = " ".join([pathjoin(out_dir, f) for f in self.get_compile_dependencies()])
        compileargs = " ".join(self.compileargs)
        print(f"{obj_file}: {self.fullpath} {includes}")
        print(f"\t$(CXX) $(CXXFLAGS) $(PB_INCLUDES) {compileargs} -I{src_dir} -I{out_dir} -c $< -o $@")
        print()
        emitted = Emitted(directories=[os.path.dirname(obj_file)])
        if self.__is_link_target:
            executable = pathjoin(out_dir, self.swap_extension(""))
            deps = " ".join([pathjoin(out_dir, x) for x in self.get_link_dependencies()])
            linkargs = " ".join(list(self.get_linkargs()) + self.linkargs)
            print(f"{executable}: {deps} {obj_file}")
            print(f"\t$(CXX) $(CXXFLAGS) -o $@ $^ $(PB_LIBS) {linkargs} -pthread")
            print()
            emitted.executables = [executable]
        return emitted

@handles(extension=".c", produces=[".o"])
class CFile(File):

    def initialize(self, contents):
        self.includes = get_includes(contents)
        self.compileargs = get_compileargs(contents)
        self.linkargs = get_linkargs(contents)

    def get_aliases(self):
        return [self.filename, self.swap_extension(".h")]

    def has_relation(self, file):
        if self.swap_extension(".h") == file.filename:
            return FileAction.DROP
        return FileAction.INCOMPATIBLE

    def emit(self, out_dir):
        obj_file = pathjoin(out_dir, self.swap_extension(".o"))
        includes = " ".join([pathjoin(out_dir, f) for f in self.get_compile_dependencies()])
        compileargs = " ".join(self.compileargs)
        print(f"{obj_file}: {self.fullpath} {includes}")
        print(f"\t$(CC) $(CFLAGS) -I{src_dir} -I{out_dir} {compileargs} -c $< -o $@")
        print()
        return Emitted(directories=[os.path.dirname(obj_file)])

@handles(extension=".h")
class HeaderFile(File):

    def initialize(self, contents):
        self.includes = filter(lambda s: s not in self.get_aliases(), get_includes(contents))

    def has_relation(self, file):
        if self.base == file.base and file.extension in [CCFile.extension, CFile.extension]:
            return FileAction.REPLACE
        return FileAction.INCOMPATIBLE

    def emit(self, out_dir):
        build_dir = pathjoin(out_dir, self.dirname)
        dst = pathjoin(build_dir, "%.h")
        src = pathjoin(src_dir, self.dirname, "%.h")

        pattern = f"{dst}: {src}\n" \
                  f"\tcp $< $@\n"

        return Emitted(directories=[build_dir], patterns=[pattern])


@handles(extension=".cch", produces=[".cch.o"])
class CCHFile(File):

    def initialize(self, contents):
        self.includes = filter(lambda s: not s in self.get_aliases(), get_includes(contents))
        self.compileargs = get_compileargs(contents)
        self.linkargs = get_linkargs(contents)

    def get_aliases(self):
        return [self.filename, self.filename + ".h"]

    def emit(self, out_dir):
        (cc_file, obj_file) = self.get_variants([".cch.cc", ".cch.o"],
                                                prepend_dir=out_dir)
        includes = " ".join([pathjoin(out_dir, f) for f in self.get_compile_dependencies()])
        compileargs = " ".join(self.compileargs)

        build_dir = pathjoin(out_dir, self.dirname)
        output_base = pathjoin(build_dir, "%.cch")
        src_pattern = pathjoin(src_dir, self.dirname, "%.cch")
        include_path = pathjoin(self.dirname, "%f")

        pattern = f"{output_base}.cc {output_base}.h: {src_pattern}\n" \
                  f"\t$(CCH) --input $< --include={include_path} --output={build_dir}/%f\n"

        print(f"{obj_file}: {cc_file} {includes}")
        print(f"\t$(CXX) $(CXXFLAGS) $(PB_INCLUDES) -I{src_dir} -I{out_dir} {compileargs} -c $< -o $@")
        print()
        return Emitted(directories=[build_dir], patterns=[pattern])


@handles(extension=".proto", produces=[".grpc.pb.o", ".pb.o"])
class ProtobufFile(File):

    def initialize(self, contents):
        self.includes = get_imports(contents)

    def get_aliases(self):
        return [self.filename, self.swap_extension(".pb.h"), self.swap_extension(".grpc.pb.h")]

    def emit(self, out_dir):
        (grpc_cc, grpc_o) = self.get_variants([".grpc.pb.cc", ".grpc.pb.o"],
                                              prepend_dir=out_dir)
        (pb_cc, pb_o) = self.get_variants([".pb.cc", ".pb.o"],
                                          prepend_dir=out_dir)

        build_dir = pathjoin(out_dir, self.dirname)
        src = pathjoin(src_dir, self.dirname, "%.proto")
        variants = " ".join([pathjoin(build_dir, x) for x in ["%.grpc.pb.cc", "%.grpc.pb.h", "%.pb.cc", "%.pb.h"]])
        pattern = f"{variants}: {src}\n" \
                  f"\t$(PROTOC) --grpc_out={out_dir} --cpp_out={out_dir} -I{src_dir} $<\n"

        deps = " ".join([pathjoin(out_dir, x) for x in self.get_compile_dependencies()])
        for (cc_file, obj_file) in [(pb_cc, pb_o), (grpc_cc, grpc_o)]:
            print(f"{obj_file}: {cc_file} {deps}")
            print(f"\t$(CXX) $(CXXFLAGS) $(PB_INCLUDES) -I{out_dir} -c $< -o $@")
        print()
        return Emitted(directories=[build_dir], patterns=[pattern])


def find_files(root_dir, extensions):
    """ Return all files under a subdirectory
        that match the extensions filter. """
    for (dirname, subdirs, files) in os.walk(root_dir, topdown=False):
        # Yield each file that matches the extensions list.
        for filename in files:
            (_, extension) = os.path.splitext(filename)
            if extension in extensions:
                yield pathjoin(dirname, filename)
        # Recurse into each subdirectory.
        for subdir in subdirs:
            find_files(pathjoin(root_dir, subdir), extensions)



if __name__ == "__main__":

    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("src_root", help="Base directory of source tree")
    parser.add_argument("build_root", help="Base directory of build output")
    parser.add_argument("--std", default="c++11", help="C++ version")
    parser.add_argument("--cstd", default="c11", help="C version")
    parser.add_argument("--optimization", default="2", help="Optimization level (-OX)")
    parser.add_argument("--debug", action="store_true", help="Debug logging to stderr")
    args = parser.parse_args()

    # Set the two global variables.
    globals()["debug"] = lambda s: print(f">> {s}", file=sys.stderr) if args.debug else None
    src_dir = args.src_root

    # Print the normal Makefile pre-amble - setting of tool names, flags, etc.
    # The default target is 'all', which is a list of all linkable executables.
    # Also provides a 'clean' target which removes the build directory.
    print(dedent(f"""\
    CC ?= gcc
    CXX ?= g++
    CCH ?= cch
    CFLAGS = -std={args.cstd} -O{args.optimization} -Wall -Wextra -Werror
    CXXFLAGS = -g -std={args.std} -O{args.optimization} -Wall -Wextra -Werror -Wno-unused-parameter -Wno-sign-compare

    PROTOC ?= ./grpc/cmake/build/third_party/protobuf/protoc --plugin=protoc-gen-grpc=grpc/cmake/build/grpc_cpp_plugin

    PB_INCLUDES = -Igrpc/include/ -Igrpc/third_party/protobuf/src/
    PB_LIBS = -Lgrpc/cmake/build/ -lprotobuf $(shell PKG_CONFIG_PATH=grpc/cmake/build/libs/opt/pkgconfig/ pkg-config --libs-only-l grpc++_unsecure) -lupb -lcares -lz -laddress_sorting

    .PHONY: default
    default: all

    .PHONY: clean
    clean:
    \trm -rf {args.build_root}
    """))

    files = []
    file_map = {}

    # Enumerate the set of files in the source root that
    # we are interested in putting into the Makefile.
    for filename in find_files(src_dir, file_types.keys()):
        with open(filename, "r") as f:
            contents = f.read()

        (_, extension) = os.path.splitext(filename)
        file_class = file_types.get(extension)
        file = file_class(filename, contents)
        files.append(file)

        for alias in file.get_aliases():
            in_map = file_map.get(alias, None)
            if in_map:
                action = in_map.has_relation(file)
                if action == FileAction.INCOMPATIBLE:
                    raise Exception(f"{alias} ({type(in_map).__name__}) already exists"
                                    f"in file map as {in_map} ({type(in_map).__name__})")
                elif action == FileAction.DROP:
                    continue
                # Otherwise the action is REPLACE, so drop through and replace it.

            file_map[alias] = file

    # Resolve the dependency tree.
    for file in files:
        for include in file.includes:
            if include not in file_map:
                raise Exception(f"{file.filename} references unknown file {include}")
            include = file_map[include]
            # Don't add a file as a dependency of itself.
            if include is not file:
                file.dependencies.append(include)


    executables = []
    build_directories = set()
    patterns = set()
    dir_targets = defaultdict(list)

    # Loop over the files and emit their Makefile stanzas.
    # This is done separately because the first time a file
    # is encountered in the initial loop above, it is unlikely
    # to have a full picture of its recursive dependencies.
    for file in files:
        cd = file.get_compile_dependencies()
        ld = file.get_link_dependencies()
        assert len(cd) == len(set(cd)), f"cd: {cd}"
        assert len(ld) == len(set(ld)), f"ld: {ld}"

        emitted = file.emit(args.build_root)
        assert isinstance(emitted, Emitted), \
            "emit() must return an Emitted object"
        if emitted.executables:
            executables += emitted.executables
            for executable in emitted.executables:
                dir_targets[os.path.dirname(executable)].append(executable)
        if emitted.directories:
            build_directories.update(emitted.directories)
        if emitted.patterns:
            patterns.update(emitted.patterns)

    for pattern in patterns:
        print(pattern)

    # Print a list of convenience directory build targets
    # that depend on all of the executables in that directory.
    for (dir, products) in dir_targets.items():
        print(f"{dir} {dir}/: {' '.join(products)}")
        print()

    # Print the Makefile post-amble.  Include all of the
    # executable targets in the default Makefile target.
    # Output a target to make the directory structure in
    # the build directory.
    #build_directories = " \\\n    \t".join(build_directories)
    executables = " \\\n    \t".join(executables)
    print(dedent(f"""\
    .PHONY: builddirs
    builddirs:
    \t@mkdir -p

    .PHONY: all
    all: \
    \t{executables}
    """));

    # Make sure the directory structure in the build directory
    # is in place.  This helps tools/compilers that won't build
    # directory structure on their own.
    for build_dir in build_directories:
        pathlib.Path(build_dir).mkdir(parents=True, exist_ok=True)
