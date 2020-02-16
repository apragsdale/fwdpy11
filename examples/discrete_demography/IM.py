#
# Copyright (C) 2020 Kevin Thornton <krthornt@uci.edu>
#
# This file is part of fwdpy11.
#
# fwdpy11 is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# fwdpy11 is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with fwdpy11.  If not, see <http://www.gnu.org/licenses/>.
#

import fwdpy11
import fwdpy11.demographic_models.IM
import argparse
import moments
import sys
import numpy as np
import concurrent.futures
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec


def make_parser():
    ADHF = argparse.ArgumentDefaultsHelpFormatter
    parser = argparse.ArgumentParser("IM.py", formatter_class=ADHF)
    parser.add_argument('--split', '-s', type=float,
                        help="Fraction that splits into deme 0")
    parser.add_argument('--tsplit', '-T', type=float,
                        help="Time since population split,"
                        " in units of Nref generations")
    parser.add_argument('--seed', type=int, help="Random number seed")

    optional = parser.add_argument_group("Optional")
    optional.add_argument('--Nref', type=int, default=1000,
                          help="Ancestral population size")
    optional.add_argument('--N0', type=float, default=1.0,
                          help="Contemporary size of deme 0, relative to Nref")
    optional.add_argument('--N1', type=float, default=1.0,
                          help="Contemporary size of deme 1, relative to Nref")
    optional.add_argument('--gamma', type=float, help="2Ns")
    # Require 0 <= h <= 2
    optional.add_argument('-H', type=float, default=1.0, help="Dominance")
    optional.add_argument('--nreps', type=int, default=1,
                          help="Number of forward simulation replicates")
    optional.add_argument('--migrates', '-M', type=float,
                          nargs=2, default=[0., 0.],
                          help="Migration rates")
    optional.add_argument('--nsam', type=int, default=15,
                          help="Number of diploids to sample from each deme")
    optional.add_argument('--theta', type=float, default=1.0,
                          help="Scaled mutation rate. "
                          "Danger zone with selection :).")
    optional.add_argument('--rho', type=float, default=1e3,
                          help="Scaled recombination rate, rho = 4*Nref*r")

    return parser


def IM_moments(params, ns, gamma=0.0, h=0.5):
    """
    Expected FS for IM model with selection

    ns: sample sizes, given as [ns1, ns2]
    s: frac that splits into deme 1 (1-s into deme 2)
    nu1/nu2: contemporary population sizes, with exponenential size change
    T: time between split and now (in 2Nref generations)
    m12/m21: migration rates, scaled by 2Nref
             mij is rate from j into i

    The mutation rate theta=4*N_ref*u is assumed to be 1.

    ns: the sample sizes (don't have to be equal) given as list of length 2

    gamma: pop-size scaled selection coefficient (2Ns), default 0
    h: dominance coefficient, default 0.5

    Note that when integrating, gamma and h must be passed as lists of same
    length as number of demes, with each entry specifying the coefficient in
    each deme. If they are all the same, pass
        `gamma=[gamma, gamma, ..., gamma], h=[h, h, ..., h]`
    where the lengths are equal to the number of demes.

    gamma = 2*N_ref*s, with the interpretation of fitnesses:
        aa : 1
        Aa : 1+2hs
        AA : 1+2s
    """
    s, nu1, nu2, T, m12, m21 = params
    # equilibrium frequency spectrum
    sts = moments.LinearSystem_1D.steady_state_1D(
        ns[0] + ns[1], gamma=gamma, h=h)
    fs = moments.Spectrum(sts)
    # split into two demes
    fs = moments.Manips.split_1D_to_2D(fs, ns[0], ns[1])
    # define size change function
    A, B = 1., 1.
    if s is not None:
        A, B = 1.0 - s, s

    def nu1_func(t): return A * np.exp(np.log(nu1/A)*t/T)

    def nu2_func(t):
        return B * np.exp(np.log(nu2/B)*t/T)

    def nu_func(t): return [nu1_func(t), nu2_func(t)]
    # integrate for time T
    fs.integrate(nu_func, T, m=np.array([[0, m12], [m21, 0]]),
                 gamma=[gamma, gamma], h=[h, h])
    return fs


def build_demography(args):
    """
    Returns the demography, the simulation length, and the
    final total size in each deme.

    The main real work here is to convert the input
    paremeters to match the scaling expected by
    fwdpy11.demographic_models.IM.two_deme_IM:

    1. The input migration rates are in units of 2*Nref
    2. The time since the split is also in units of 2*Nref
    """
    two_deme_IM = fwdpy11.demographic_models.IM.two_deme_IM

    # Rescale input migration rates
    migrates = tuple(i/(2.*args.Nref) for i in args.migrates)

    # Change split time from generations/(2*Nref) to
    # generations/Nref.
    d, t1, t2 = two_deme_IM(args.Nref, 2.0*args.tsplit, args.split,
                            (args.N0, args.N1), migrates)
    simlen = int(t1 + t2)
    N0 = np.rint(args.N0*args.Nref).astype(int)
    N1 = np.rint(args.N1*args.Nref).astype(int)
    return d, simlen, (N0, N1)


def build_parameters_dict(args):
    """
    Returns sim params and the final sizes
    in each deme
    """
    demog, simlen, finalNs = build_demography(args)

    nregions = []
    sregions = []
    recregions = [fwdpy11.PoissonInterval(0, 1, args.rho/(4.*args.Nref))]

    rates = (0, 0, None)
    if args.gamma is not None:
        sregions = [fwdpy11.ConstantS(
            0, 1, 1, args.gamma, args.H, scaling=2*args.Nref)]
        rates = (0, args.theta/(4.0*args.Nref), None)

    pdict = {'nregions': nregions,
             'sregions': sregions,
             'recregions': recregions,
             'rates': rates,
             'gvalue': fwdpy11.Multiplicative(2.),
             'demography': demog,
             'simlen': simlen,
             'prune_selected': True
             }

    return pdict, finalNs


def per_deme_sfs(pop):
    """
    Get the marginal SFS per deme.
    """
    samples = pop.alive_nodes
    nt = np.array(pop.tables.nodes, copy=False)
    for i in pop.diploid_metadata:
        assert i.deme == nt['deme'][i.nodes[0]]
        assert i.deme == nt['deme'][i.nodes[1]]

    deme_sizes = pop.deme_sizes()
    assert np.sum(deme_sizes[1]) == pop.N
    deme_sfs = {}
    for i, j in zip(deme_sizes[0], deme_sizes[1]):
        deme_sfs[i] = np.zeros(2*j + 1)

    ti = fwdpy11.TreeIterator(pop.tables, samples, update_samples=True)
    nt = np.array(pop.tables.nodes, copy=False)
    nmuts = 0
    for tree in ti:
        for mut in tree.mutations():
            sb = tree.samples_below(mut.node)
            assert all([i in samples for i in sb]) is True
            dc = np.unique(nt['deme'][sb], return_counts=True)
            assert dc[1].sum() == len(sb), f"{dc[1].sum} {len(sb)}"
            nmuts += 1
            for deme, daf in zip(dc[0], dc[1]):
                deme_sfs[deme][daf] += 1
    assert nmuts == len(pop.tables.mutations)
    return deme_sfs[0], deme_sfs[1]


def subsample_sfs(pop, args):
    md = np.array(pop.diploid_metadata, copy=False)
    nodes0 = md['nodes'][np.where(md['deme'] == 0)[0]].flatten()
    nodes1 = md['nodes'][np.where(md['deme'] == 1)[0]].flatten()

    s0 = np.random.choice(nodes0, 2*args.nsam, replace=False)
    s1 = np.random.choice(nodes1, 2*args.nsam, replace=False)

    samples = np.array(s0.tolist() + s1.tolist())
    sfs = {0: np.zeros(len(s0)-1), 1: np.zeros(len(s1)-1)}
    ti = fwdpy11.TreeIterator(pop.tables, samples, update_samples=True)
    nt = np.array(pop.tables.nodes, copy=False)
    nmuts = 0
    for tree in ti:
        for mut in tree.mutations():
            sb = tree.samples_below(mut.node)
            assert all([i in samples for i in sb]) is True
            dc = np.unique(nt['deme'][sb], return_counts=True)
            assert dc[1].sum() == len(sb), f"{dc[1].sum} {len(sb)}"
            nmuts += 1
            for deme, daf in zip(dc[0], dc[1]):
                if daf < 2*args.nsam:
                    sfs[deme][daf-1] += 1
    assert nmuts == len(pop.tables.mutations)
    return sfs[0], sfs[1]


def project_sfs(sfs, n):
    fs = moments.Spectrum(sfs)
    psfs = fs.project([n])
    return psfs.data[1:-1]


def runsim(args, pdict, seed):
    pop = fwdpy11.DiploidPopulation(args.Nref, 1.0)
    rng = fwdpy11.GSLrng(seed)
    np.random.seed(seed)

    params = fwdpy11.ModelParams(**pdict)
    fwdpy11.evolvets(rng, pop, params, 100)
    if args.gamma is None:
        fwdpy11.infinite_sites(rng, pop, args.theta/float(4.*args.Nref))
    sfs0, sfs1 = per_deme_sfs(pop)
    sfs0_rs, sfs1_rs = subsample_sfs(pop, args)
    return sfs0, sfs1, sfs0_rs, sfs1_rs


def plot_sfs(args, moments_fs, fwdpy11_fs, fwdpy11_sample_sfs):
    fwdpy11_fs0 = project_sfs(fwdpy11_fs[0], 2*args.nsam)
    fwdpy11_fs1 = project_sfs(fwdpy11_fs[1], 2*args.nsam)
    moments_fs0 = moments_fs.marginalize([1])
    moments_fs1 = moments_fs.marginalize([0])

    fig = plt.figure(figsize=(7, 5))
    gs = gridspec.GridSpec(ncols=2, nrows=1, figure=fig)
    deme0 = fig.add_subplot(gs[0, 0])
    deme1 = fig.add_subplot(gs[0, 1])
    x = [i for i in range(2*args.nsam-1)]
    deme0.plot(x, fwdpy11_fs0, 'bo',
               label="fwdpy11 projected", alpha=0.2, zorder=2)
    deme0.plot(x, fwdpy11_sample_sfs[0], 'go',
               label="fwdpy11 sample", alpha=0.2, zorder=3)
    deme0.plot(x, args.theta*moments_fs0.data[1:-1],
               'r-', alpha=0.2, label="moments", zorder=1)
    deme0.plot(x, args.theta*moments_fs0.data[1:-1], 'r+', zorder=1)

    deme1.plot(x, fwdpy11_fs1, 'bo',
               label="fwdpy11 projected", alpha=0.2, zorder=2)
    deme1.plot(x, fwdpy11_sample_sfs[1], 'go',
               label="fwdpy11 sample", alpha=0.2,  zorder=3)
    deme1.plot(x, args.theta*moments_fs1.data[1:-1],
               'r-', alpha=0.2, label="moments", zorder=1)
    deme1.plot(x, args.theta*moments_fs1.data[1:-1], 'r+', zorder=1)
    deme0.set_title("Deme 0")
    deme1.set_title("Deme 1")
    deme0.legend()
    deme1.legend()
    deme0.set_xlabel("Derived frequency")
    deme1.set_xlabel("Derived frequency")
    deme0.set_ylabel("E[# mutations]")
    plt.tight_layout()
    plt.savefig("moments.png")


if __name__ == "__main__":
    parser = make_parser()
    args = parser.parse_args(sys.argv[1:])

    moments_params = (args.split, args.N0, args.N1, args.tsplit,
                      args.migrates[1], args.migrates[0])
    moments_nsam = (2*args.nsam, 2*args.nsam)
    mgamma = args.gamma
    if mgamma is None:
        mgamma = 0.0
    moments_fs = IM_moments(moments_params, moments_nsam,
                            mgamma, args.H/2.0)

    # Fail early if input params are bad
    pdict, finalNs = build_parameters_dict(args)
    np.random.seed(args.seed)
    seeds = np.random.randint(0, np.iinfo(np.uint32).max, args.nreps)

    sum_sfs0 = np.zeros(2*finalNs[0]+1)
    sum_sfs1 = np.zeros(2*finalNs[1]+1)
    sum_samples_sfs0 = np.zeros(2*args.nsam-1)
    sum_samples_sfs1 = np.zeros(2*args.nsam-1)
    with concurrent.futures.ProcessPoolExecutor() as e:
        futures = {e.submit(runsim, args, pdict, i) for i in seeds}
        for fut in concurrent.futures.as_completed(futures):
            sfs0, sfs1, sfs0_rs, sfs1_rs = fut.result()
            sum_sfs0 += sfs0
            sum_sfs1 += sfs1
            sum_samples_sfs0 += sfs0_rs
            sum_samples_sfs1 += sfs1_rs

    sum_sfs0 /= args.nreps
    sum_sfs1 /= args.nreps
    sum_samples_sfs0 /= args.nreps
    sum_samples_sfs1 /= args.nreps

    plot_sfs(args, moments_fs, (sum_sfs0, sum_sfs1),
             (sum_samples_sfs0, sum_samples_sfs1))
