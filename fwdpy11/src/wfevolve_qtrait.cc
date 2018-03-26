//
// Copyright (C) 2017 Kevin Thornton <krthornt@uci.edu>
//
// This file is part of fwdpy11.
//
// fwdpy11 is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// fwdpy11 is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with fwdpy11.  If not, see <http://www.gnu.org/licenses/>.
//
#include <fwdpy11/types.hpp>
#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/functional.h>
#include <pybind11/stl.h>
#include <functional>
#include <tuple>
#include <queue>
#include <cmath>
#include <stdexcept>
#include <fwdpp/diploid.hh>
#include <fwdpp/sugar/GSLrng_t.hpp>
#include <fwdpp/extensions/regions.hpp>
#include <fwdpy11/samplers.hpp>
#include <fwdpy11/fitness/fitness.hpp>
#include <fwdpy11/rules/qtrait.hpp>
#include <fwdpy11/sim_functions.hpp>
#include <fwdpy11/evolve/qtrait_api.hpp>
#include <fwdpy11/evolve/slocuspop.hpp>
#include <fwdpy11/evolve/mlocuspop.hpp>
#include <fwdpy11/multilocus.hpp>

namespace py = pybind11;

// Evolve the population for some amount of time with mutation and
// recombination
void
evolve_singlepop_regions_qtrait_cpp(
    const fwdpy11::GSLrng_t &rng, fwdpy11::singlepop_t &pop,
    py::array_t<std::uint32_t> popsizes, const double mu_neutral,
    const double mu_selected, const double recrate,
    const fwdpp::extensions::discrete_mut_model &mmodel,
    const fwdpp::extensions::discrete_rec_model &rmodel,
    fwdpy11::single_locus_fitness &fitness,
    fwdpy11::singlepop_temporal_sampler recorder, const double selfing_rate,
    fwdpy11::trait_to_fitness_function trait_to_fitness,
    py::object trait_to_fitness_updater,
    fwdpy11::single_locus_noise_function noise, py::object noise_updater,
    const bool remove_selected_fixations)
{
    bool updater_exists = false;
    py::function updater;
    if (!trait_to_fitness_updater.is_none())
        {
            updater = py::function(trait_to_fitness_updater);
            updater_exists = true;
        }
    bool noise_updater_exists = false;
    py::function noise_updater_fxn;
    if (!noise_updater.is_none())
        {
            noise_updater_fxn = noise_updater;
            noise_updater_exists = true;
        }
    const auto generations = popsizes.size();
    if (!generations)
        throw std::runtime_error("empty list of population sizes");
    if (mu_neutral < 0.)
        {
            throw std::runtime_error("negative neutral mutation rate: "
                                     + std::to_string(mu_neutral));
        }
    if (mu_selected < 0.)
        {
            throw std::runtime_error("negative selected mutation rate: "
                                     + std::to_string(mu_selected));
        }
    if (recrate < 0.)
        {
            throw std::runtime_error("negative recombination rate: "
                                     + std::to_string(recrate));
        }
    const auto fitness_callback = fitness.callback();
    pop.mutations.reserve(std::ceil(
        std::log(2 * pop.N)
        * (4. * double(pop.N) * (mu_neutral + mu_selected)
           + 0.667 * (4. * double(pop.N) * (mu_neutral + mu_selected)))));

    const auto mmodels = fwdpp::extensions::bind_dmm(
        mmodel, pop.mutations, pop.mut_lookup, rng.get(), mu_neutral,
        mu_selected, &pop.generation);
    ++pop.generation;
    auto rules = fwdpy11::qtrait::qtrait_model_rules(trait_to_fitness, noise);
    fitness.update(pop);
    auto wbar = rules.w(pop, fitness_callback);
    if (!std::isfinite(wbar))
        {
            throw std::runtime_error("population mean fitness not finite");
        }
    for (unsigned generation = 0; generation < generations;
         ++generation, ++pop.generation)
        {
            const auto N_next = popsizes.at(generation);
            if (!remove_selected_fixations)
                {
                    fwdpy11::evolve_generation(
                        rng, pop, N_next, mu_neutral + mu_selected, mmodels,
                        rmodel,
                        std::bind(&fwdpy11::qtrait::qtrait_model_rules::pick1,
                                  &rules, std::placeholders::_1,
                                  std::placeholders::_2),
                        std::bind(&fwdpy11::qtrait::qtrait_model_rules::pick2,
                                  &rules, std::placeholders::_1,
                                  std::placeholders::_2, std::placeholders::_3,
                                  selfing_rate),
                        std::bind(&fwdpy11::qtrait::qtrait_model_rules::update,
                                  &rules, std::placeholders::_1,
                                  std::placeholders::_2, std::placeholders::_3,
                                  std::placeholders::_4,
                                  std::placeholders::_5),
                        fwdpp::remove_neutral());
                }
            else
                {
                    fwdpy11::evolve_generation(
                        rng, pop, N_next, mu_neutral + mu_selected, mmodels,
                        rmodel,
                        std::bind(&fwdpy11::qtrait::qtrait_model_rules::pick1,
                                  &rules, std::placeholders::_1,
                                  std::placeholders::_2),
                        std::bind(&fwdpy11::qtrait::qtrait_model_rules::pick2,
                                  &rules, std::placeholders::_1,
                                  std::placeholders::_2, std::placeholders::_3,
                                  selfing_rate),
                        std::bind(&fwdpy11::qtrait::qtrait_model_rules::update,
                                  &rules, std::placeholders::_1,
                                  std::placeholders::_2, std::placeholders::_3,
                                  std::placeholders::_4,
                                  std::placeholders::_5),
                        std::true_type());
                }
            pop.N = N_next;
            fwdpy11::update_mutations(
                pop.mutations, pop.fixations, pop.fixation_times,
                pop.mut_lookup, pop.mcounts, pop.generation, 2 * pop.N, false);
            fitness.update(pop);
            wbar = rules.w(pop, fitness_callback);
            if (!std::isfinite(wbar))
                {
                    throw std::runtime_error(
                        "population mean fitness not finite");
                }
            recorder(pop);
            if (updater_exists)
                {
                    updater(pop);
                }
            if (noise_updater_exists)
                {
                    noise_updater_fxn(pop);
                }
        }
    --pop.generation;
}

void
evolve_qtrait_mloc_regions_cpp(
    const fwdpy11::GSLrng_t &rng, fwdpy11::multilocus_t &pop,
    py::array_t<std::uint32_t> popsizes,
    const std::vector<double> &neutral_mutation_rates,
    const std::vector<double> &selected_mutation_rates,
    const std::vector<double> &recrates,
    const std::vector<fwdpp::extensions::discrete_mut_model> &mmodels,
    const std::vector<fwdpp::extensions::discrete_rec_model> &rmodels,
    py::list interlocus_rec_wrappers,
    // const std::vector<std::function<unsigned(void)>> &interlocus_rec,
    fwdpy11::multilocus_genetic_value &multilocus_gvalue,
    fwdpy11::multilocus_temporal_sampler recorder, const double selfing_rate,
    fwdpy11::multilocus_aggregator_function aggregator,
    fwdpy11::trait_to_fitness_function trait_to_fitness,
    py::object trait_to_fitness_updater,
    fwdpy11::multilocus_noise_function noise, py::object noise_updater,
    const bool remove_selected_fixations)
{
    bool updater_exists = false;
    py::function updater;
    if (!trait_to_fitness_updater.is_none())
        {
            updater = py::function(trait_to_fitness_updater);
            updater_exists = true;
        }
    bool noise_updater_exists = false;
    py::function noise_updater_fxn;
    if (!noise_updater.is_none())
        {
            noise_updater_fxn = noise_updater;
            noise_updater_exists = true;
        }
    const auto generations = popsizes.size();
    if (!generations)
        throw std::runtime_error("empty list of population sizes");
    auto bound_mmodels = fwdpp::extensions::bind_vec_dmm(
        mmodels, pop.mutations, pop.mut_lookup, rng.get(),
        neutral_mutation_rates, selected_mutation_rates, &pop.generation);
    std::vector<double> total_mut_rates(neutral_mutation_rates);
    std::transform(total_mut_rates.cbegin(), total_mut_rates.cend(),
                   selected_mutation_rates.cbegin(), total_mut_rates.begin(),
                   std::plus<double>());

    fwdpy11::qtrait::qtrait_mloc_rules rules(aggregator, trait_to_fitness,
                                             noise);

    ++pop.generation;
    multilocus_gvalue.update(pop);
    auto wbar = rules.w(pop, multilocus_gvalue);
    if (!std::isfinite(wbar))
        {
            throw std::runtime_error("population mean fitness not finite");
        }
    std::vector<std::function<unsigned(void)>> interlocus_rec;
    for (auto &&i : interlocus_rec_wrappers)
        {
            interlocus_rec.push_back(
                py::cast<fwdpy11::interlocus_rec>(i).callback(rng));
        }

    for (unsigned i = 0; i < generations; ++i, ++pop.generation)
        {
            auto N_next = popsizes.at(i);
            if (!remove_selected_fixations)
                {
                    fwdpy11::evolve_generation(
                        rng, pop, N_next, total_mut_rates, bound_mmodels,
                        rmodels, interlocus_rec,
                        std::bind(&fwdpy11::qtrait::qtrait_mloc_rules::pick1,
                                  &rules, std::placeholders::_1,
                                  std::placeholders::_2),
                        std::bind(&fwdpy11::qtrait::qtrait_mloc_rules::pick2,
                                  &rules, std::placeholders::_1,
                                  std::placeholders::_2, std::placeholders::_3,
                                  selfing_rate),
                        std::bind(&fwdpy11::qtrait::qtrait_mloc_rules::update,
                                  &rules, std::placeholders::_1,
                                  std::placeholders::_2, std::placeholders::_3,
                                  std::placeholders::_4,
                                  std::placeholders::_5),
                        fwdpp::remove_neutral());
                }
            else
                {
                    fwdpy11::evolve_generation(
                        rng, pop, N_next, total_mut_rates, bound_mmodels,
                        rmodels, interlocus_rec,
                        std::bind(&fwdpy11::qtrait::qtrait_mloc_rules::pick1,
                                  &rules, std::placeholders::_1,
                                  std::placeholders::_2),
                        std::bind(&fwdpy11::qtrait::qtrait_mloc_rules::pick2,
                                  &rules, std::placeholders::_1,
                                  std::placeholders::_2, std::placeholders::_3,
                                  selfing_rate),
                        std::bind(&fwdpy11::qtrait::qtrait_mloc_rules::update,
                                  &rules, std::placeholders::_1,
                                  std::placeholders::_2, std::placeholders::_3,
                                  std::placeholders::_4,
                                  std::placeholders::_5),
                        std::true_type());
                }
            pop.N = N_next;
            fwdpy11::update_mutations(
                pop.mutations, pop.fixations, pop.fixation_times,
                pop.mut_lookup, pop.mcounts, pop.generation, 2 * pop.N, false);
            multilocus_gvalue.update(pop);
            wbar = rules.w(pop, multilocus_gvalue);
            recorder(pop);
            if (updater_exists)
                {
                    updater(pop);
                }
            if (noise_updater_exists)
                {
                    noise_updater_fxn(pop);
                }
        }
    --pop.generation;
}

PYBIND11_MODULE(wfevolve_qtrait, m)
{
    m.doc() = "Evolution of quantitative traits under a Wright-Fisher model.";

    m.def("evolve_singlepop_regions_qtrait_cpp",
          &evolve_singlepop_regions_qtrait_cpp);

    m.def("evolve_qtrait_mloc_regions_cpp", &evolve_qtrait_mloc_regions_cpp);
}
