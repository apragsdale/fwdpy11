#We use cppimport to build the module.
#For the sake of unit testing, we force
#a rebuild every time, but that clearly
#wouldn't be needed for normal use.
import cppimport
cppimport.force_rebuild()
cppimport.set_quiet(False)
snowdrift = cppimport.imp("snowdrift")
import unittest
import numpy as np
import fwdpy11 as fp11
import fwdpy11.temporal_samplers as fp11ts
import fwdpy11.wright_fisher
import fwdpy11.ezparams

def evolve_snowdrift(args):
    """
    We write the function taking a tuple 
    out of habit, simplifying later
    integration with multiprocessing or
    concurrent.futures.
    """
    N,seed=args
    #Construct as single-deme object
    #with N diploids
    pop = fp11.SlocusPop(N)
    #Initialize a random number generator
    rng=fp11.GSLrng(seed)
    p={'sregions':[fp11.ExpS(0,1,1,-0.1,1.0)],
       'recregions':[fp11.Region(0,1,1)],
       'nregions':[],
       'gvalue':snowdrift.SlocusSnowdrift(0.2,-0.2,1,-2),
        #evolve for 100 generations so that unit tests are
        #fast
       'demog':np.array([N]*100,dtype=np.uint32),
       'rates':(0.0,0.0025,0.001),
       'prune_selected':False
       }
    params = fwdpy11.model_params.SlocusParams(**p)
    fp11.wright_fisher.evolve(rng,pop,params)
    #return our pop
    return pop

class testSnowdrift(unittest.TestCase):
    def test_create(self):
        f = snowdrift.SlocusSnowdrift(1,-1,0.1,0.2);
    def test_evolve(self):
        p = evolve_snowdrift((1000,42))

if __name__=="__main__":
    unittest.main()
