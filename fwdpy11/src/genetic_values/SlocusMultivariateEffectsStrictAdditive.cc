#include <pybind11/pybind11.h>
#include <fwdpy11/genetic_values/SlocusMultivariateEffectsStrictAdditive.hpp>

namespace py = pybind11;

void
init_SlocusMultivariateEffectsStrictAdditive(py::module& m)
{
    py::class_<fwdpy11::SlocusMultivariateEffectsStrictAdditive,
               fwdpy11::SlocusPopMultivariateGeneticValueWithMapping>(
        m, "SlocusMultivariateEffectsStrictAdditive")
        .def(py::init<std::size_t, std::size_t,
                      const fwdpy11::MultivariateGeneticValueToFitnessMap&>(),
             py::arg("ndimensions"), py::arg("focal_trait"),
             py::arg("genetic_values_to_fitness_map"))
        .def(py::init<std::size_t, std::size_t,
                      const fwdpy11::MultivariateGeneticValueToFitnessMap&,
                      const fwdpy11::GeneticValueNoise&>(),
             py::arg("ndimensions"), py::arg("focal_trait"),
             py::arg("genetic_values_to_fitness_map"), py::arg("noise"));
}
