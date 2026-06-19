#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <wchar.h>
#include <stdint.h>
#include "src/rar.hpp"

static PyObject* UnrarError;

static int is_safe_filename(const wchar_t* name) {
    if (!name || !name[0]) return 0;
    if (name[0] == L'/' || name[0] == L'\\') return 0;
    const wchar_t* p = name;
    while (*p) {
        if (p[0] == L'.' && p[1] == L'.') {
            if (p[2] == L'/' || p[2] == L'\\' || p[2] == L'\0') return 0;
        }
        if ((p[0] == L'/' || p[0] == L'\\') && p[1] == L'.' && p[2] == L'.') {
            if (p[3] == L'/' || p[3] == L'\\' || p[3] == L'\0') return 0;
        }
        p++;
    }
    return 1;
}

static PyObject* py_list_files(PyObject* self, PyObject* args, PyObject* kwargs) {
    static const char* kwlist[] = {"archive_path", "password", NULL};
    const char* archive_path = NULL;
    const char* password = NULL;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "s|z", (char**)kwlist,
                                     &archive_path, &password))
        return NULL;

    RAROpenArchiveDataEx arcData = {};
    arcData.ArcName = const_cast<char*>(archive_path);
    arcData.OpenMode = RAR_OM_LIST;

    HANDLE hArc = RAROpenArchiveEx(&arcData);
    if (!hArc || arcData.OpenResult != ERAR_SUCCESS) {
        PyErr_Format(UnrarError, "Failed to open archive (error %d)", arcData.OpenResult);
        return NULL;
    }

    if (password && password[0]) {
        RARSetPassword(hArc, const_cast<char*>(password));
    }

    PyObject* result = PyList_New(0);
    RARHeaderDataEx header = {};
    int res;

    while ((res = RARReadHeaderEx(hArc, &header)) == ERAR_SUCCESS) {
        PyObject* info = PyDict_New();
        PyDict_SetItemString(info, "filename", PyUnicode_FromWideChar(header.FileNameW, -1));
        PyDict_SetItemString(info, "file_size",
            PyLong_FromUnsignedLongLong(((uint64_t)header.UnpSizeHigh << 32) | header.UnpSize));
        PyDict_SetItemString(info, "compress_size",
            PyLong_FromUnsignedLongLong(((uint64_t)header.PackSizeHigh << 32) | header.PackSize));
        PyDict_SetItemString(info, "is_directory",
            PyBool_FromLong((header.Flags & RHDF_DIRECTORY) ? 1 : 0));
        PyList_Append(result, info);
        Py_DECREF(info);

        RARProcessFile(hArc, RAR_SKIP, NULL, NULL);
    }

    RARCloseArchive(hArc);

    if (res != ERAR_END_ARCHIVE) {
        Py_DECREF(result);
        PyErr_Format(UnrarError, "Read header failed (error %d)", res);
        return NULL;
    }
    return result;
}

static PyObject* py_extract_all(PyObject* self, PyObject* args, PyObject* kwargs) {
    static const char* kwlist[] = {"archive_path", "dest_path", "password", NULL};
    const char* archive_path = NULL;
    const char* dest_path = NULL;
    const char* password = NULL;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "ss|z", (char**)kwlist,
                                     &archive_path, &dest_path, &password))
        return NULL;

    RAROpenArchiveDataEx arcData = {};
    arcData.ArcName = const_cast<char*>(archive_path);
    arcData.OpenMode = RAR_OM_EXTRACT;

    HANDLE hArc = RAROpenArchiveEx(&arcData);
    if (!hArc || arcData.OpenResult != ERAR_SUCCESS) {
        PyErr_Format(UnrarError, "Failed to open archive (error %d)", arcData.OpenResult);
        return NULL;
    }

    if (password && password[0]) {
        RARSetPassword(hArc, const_cast<char*>(password));
    }

    int count = 0;
    int result;
    RARHeaderDataEx header = {};

    while ((result = RARReadHeaderEx(hArc, &header)) == ERAR_SUCCESS) {
        if (!is_safe_filename(header.FileNameW)) {
            RARCloseArchive(hArc);
            PyErr_Format(UnrarError, "Unsafe path in archive: %ls", header.FileNameW);
            return NULL;
        }

        result = RARProcessFile(hArc, RAR_EXTRACT, const_cast<char*>(dest_path), NULL);
        if (result != ERAR_SUCCESS) {
            RARCloseArchive(hArc);
            if (result == ERAR_MISSING_PASSWORD || result == ERAR_BAD_PASSWORD) {
                PyErr_SetString(PyExc_PermissionError, "Password required or incorrect");
            } else {
                PyErr_Format(UnrarError, "Extraction failed for %ls (error %d)", header.FileNameW, result);
            }
            return NULL;
        }
        count++;
    }

    RARCloseArchive(hArc);

    if (result != ERAR_END_ARCHIVE) {
        PyErr_Format(UnrarError, "Read header failed (error %d)", result);
        return NULL;
    }
    return PyLong_FromLong(count);
}

static PyMethodDef UnrarMethods[] = {
    {"list_files", (PyCFunction)py_list_files, METH_VARARGS | METH_KEYWORDS,
     "list_files(archive_path, password=None) -> list[dict]\n\nReturn list of file info dicts from a RAR archive."},
    {"extract_all", (PyCFunction)py_extract_all, METH_VARARGS | METH_KEYWORDS,
     "extract_all(archive_path, dest_path, password=None) -> int\n\nExtract all files from a RAR archive. Returns count of extracted files."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef unrar_module = {
    PyModuleDef_HEAD_INIT,
    "_unrar",
    "Python bindings for the UnRAR library",
    -1,
    UnrarMethods
};

PyMODINIT_FUNC PyInit__unrar(void) {
    PyObject* m = PyModule_Create(&unrar_module);
    if (m == NULL)
        return NULL;
    UnrarError = PyErr_NewException("unrar._unrar.UnrarError", NULL, NULL);
    Py_XINCREF(UnrarError);
    if (PyModule_AddObject(m, "UnrarError", UnrarError) < 0) {
        Py_XDECREF(UnrarError);
        Py_CLEAR(UnrarError);
        Py_DECREF(m);
        return NULL;
    }
    return m;
}
