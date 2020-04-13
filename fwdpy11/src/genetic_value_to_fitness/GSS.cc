#include <fwdpy11/genetic_value_to_fitness/GSS.hpp>
#include <pybind11/pybind11.h>

namespace py = pybind11;

static const auto INIT_DOUBLE =
    R"delim(
:param opt: Optimal trait value.
:type opt: float
:param VS: Strength of stabilizing selection
:type VS: float
)delim";

static const auto INIT_OPTIMUM =
    R"delim(
:param optimum: The parameters of the optimum
:type optimum: :class:`fwdpy11.Optimum`

.. versionadded:: 0.7.1
)delim";

void
init_GSS(py::module& m)
{
    py::class_<fwdpy11::GSS, fwdpy11::GeneticValueIsTrait>(
        m, "GSS", "Gaussian stabilizing selection.")
        .def(py::init<double, double>(), py::arg("opt"), py::arg("VS"), INIT_DOUBLE)
        .def(py::init<fwdpy11::Optimum>(), py::arg("optimum"), INIT_OPTIMUM)
        .def_readonly("VS", &fwdpy11::GSS::VS, "Read-only access to VS")
        .def_readonly("opt", &fwdpy11::GSS::opt,
                      "Read-only access to optimal trait value.")
        .def(py::pickle([](const fwdpy11::GSS& g) { return g.pickle(); },
                        [](py::object o) {
                            py::tuple t(o);
                            if (t.size() != 2)
                                {
                                    throw std::runtime_error("invalid object state");
                                }
                            return fwdpy11::GSS(t[0].cast<double>(),
                                                t[1].cast<double>());
                        }));
}
