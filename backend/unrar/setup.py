from setuptools import setup, Extension
import platform

UNRAR_SOURCES = [
    "rar.cpp", "strlist.cpp", "strfn.cpp", "pathfn.cpp", "smallfn.cpp",
    "global.cpp", "file.cpp", "filefn.cpp", "filcreat.cpp", "archive.cpp",
    "arcread.cpp", "unicode.cpp", "system.cpp", "crypt.cpp", "crc.cpp",
    "rawread.cpp", "encname.cpp", "resource.cpp", "match.cpp", "timefn.cpp",
    "rdwrfn.cpp", "consio.cpp", "options.cpp", "errhnd.cpp", "rarvm.cpp",
    "secpassword.cpp", "rijndael.cpp", "getbits.cpp", "sha1.cpp", "sha256.cpp",
    "blake2s.cpp", "hash.cpp", "extinfo.cpp", "extract.cpp", "volume.cpp",
    "list.cpp", "find.cpp", "unpack.cpp", "headers.cpp", "threadpool.cpp",
    "rs16.cpp", "cmddata.cpp", "ui.cpp", "largepage.cpp",
    "filestr.cpp", "scantree.cpp", "dll.cpp", "qopen.cpp",
    "rs.cpp",
]

extra_compile_args = ["-std=c++11", "-D_FILE_OFFSET_BITS=64", "-D_LARGEFILE_SOURCE", "-DRARDLL"]
extra_link_args = []

system = platform.system()
if system == "Darwin":
    extra_compile_args.append("-stdlib=libc++")
    extra_link_args.append("-stdlib=libc++")
elif system == "Windows":
    UNRAR_SOURCES.extend(["motw.cpp", "isnt.cpp"])
    extra_compile_args = ["/DRARDLL", "/DUNRAR", "/DSILENT"]
    extra_link_args = ["advapi32.lib", "shell32.lib", "ole32.lib"]

sources = ["_unrar.cpp"] + [f"src/{s}" for s in UNRAR_SOURCES]

ext = Extension(
    "unrar._unrar",
    sources=sources,
    include_dirs=["src"],
    language="c++",
    extra_compile_args=extra_compile_args,
    extra_link_args=extra_link_args,
)

setup(
    name="unrar",
    version="0.1.0",
    ext_modules=[ext],
    packages=["unrar"],
    package_dir={"unrar": "."},
    python_requires=">=3.8",
)
