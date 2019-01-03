#ifndef FWDPY11_SLOCUSPOP_MULTIVARIATE_STRICT_ADDITIVE_HPP
#define FWDPY11_SLOCUSPOP_MULTIVARIATE_STRICT_ADDITIVE_HPP

#include <vector>
#include <stdexcept>
#include <algorithm>
#include <functional>
#include "SlocusPopGeneticValueWithMapping.hpp"
#include "default_update.hpp"

namespace fwdpy11
{
    struct SlocusMultivariateEffectsStrictAdditive
        : public SlocusPopGeneticValueWithMapping
    {
        mutable std::vector<double> summed_effects;
        std::size_t focal_trait_index;

        SlocusMultivariateEffectsStrictAdditive(
            std::size_t ndim, std::size_t focal_trait,
            const GeneticValueIsTrait &gv2w_)
            : SlocusPopGeneticValueWithMapping(gv2w_),
              summed_effects(ndim, 0.0), focal_trait_index(focal_trait)
        {
        }

        SlocusMultivariateEffectsStrictAdditive(
            std::size_t ndim, std::size_t focal_trait,
            const GeneticValueIsTrait &gv2w_, const GeneticValueNoise &noise_)
            : SlocusPopGeneticValueWithMapping(gv2w_, noise_),
              summed_effects(ndim, 0.0), focal_trait_index(focal_trait)
        {
        }

        double
        calculate_gvalue(const std::size_t diploid_index,
                         const SlocusPop &pop) const
        {
            std::fill(begin(summed_effects), end(summed_effects), 0.0);

            for (auto key :
                 pop.gametes[pop.diploids[diploid_index].first].smutations)
                {
                    const auto &mut = pop.mutations[key];
                    if (mut.esizes.size() != summed_effects.size())
                        {
                            throw std::runtime_error(
                                "dimensionality mismatch");
                        }
                    std::transform(begin(mut.esizes), end(mut.esizes),
                                   begin(summed_effects),
                                   begin(summed_effects), std::plus<double>());
                }

            return summed_effects[focal_trait_index];
        }

        DEFAULT_SLOCUSPOP_UPDATE();

        pybind11::object
        pickle() const
        {
            return pybind11::none();
        }
    };
} // namespace fwdpy11

#endif
