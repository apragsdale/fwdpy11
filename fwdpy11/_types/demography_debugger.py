import fwdpy11
import numpy as np


class DemographyDebugger(object):
    """
    Debug demographic events efficiently.
    """

    def __init__(self, pop, events):
        """
        :param events: The demographic events
        :type events: :class:`fwdpy11.DiscreteDemography`
        """
        # The setup
        self.M = None
        if events.migmatrix is not None:
            self.M = np.copy(events.migmatrix.M)

        self._validate_migration_rate_change_lengths(events)

        self.maxdemes = self._get_maxdemes(pop, events)

        if self.maxdemes < 1:
            raise ValueError("Invalid number of "
                             "demes in simulation: {}".format(self.maxdemes))

        self.current_deme_sizes = np.zeros(self.maxdemes, dtype=np.uint32)
        for i, j in zip(*pop.deme_sizes()):
            self.current_deme_sizes[i] = j

        self.growth_rates = np.array([fwdpy11.NOGROWTH]*self.maxdemes)
        self.growth_onset_times = np.zeros(self.maxdemes, dtype=np.uint32)
        self.selfing_rates = np.zeros(self.maxdemes)
        # FIXME: the following is almost certainly initialized
        # incorrectly
        self.growth_initial_sizes = np.zeros(self.maxdemes, dtype=np.uint32)

        # The real work
        self.report = self._process_demographic_model(events)

    def _get_maxdemes(self, pop, events):
        """
        The maximum number of demes the sim can ever see.
        """
        md = np.array(pop.diploid_metadata, copy=False)
        max_from_md = md['deme'].max()
        max_from_events = -1

        def update_max_from_events(m, e):
            for i in e:
                try:
                    m = max(m, i.deme)
                except AttributeError:
                    m = max(m, i.source)
            return m

        for i in [events.mass_migrations, events.set_growth_rates,
                  events.set_deme_sizes, events.set_selfing_rates,
                  events.set_migration_rates]:
            max_from_events = update_max_from_events(max_from_events, i)

        current_max = max(max_from_md, max_from_events) + 1
        if self.M is None:
            return current_max

        if self.M.shape[0] < current_max:
            raise ValueError("The MigrationMatrix shape, {}, "
                             "does not match the max number of "
                             "demes present in the "
                             "simulation, ".format(self.M.shape, current_max))

        return max(current_max, self.M.shape[0])

    def _validate_migration_rate_change_lengths(self, events):
        """
        Various checks on the lengths of new migration rates.
        """
        if self.M is None and len(events.set_migration_rates) > 0:
            raise ValueError("migration rate changes are "
                             "set but there is no migration matrix")
        for i in events.set_migration_rates:
            if i.deme >= 0:
                if len(i.migrates) != self.M.shape[0]:
                    raise ValueError("Migration rates mismatch")
            else:  # Are replacing the entire matrix
                if len(i.migrates) != len(self.M.flatten()):
                    raise ValueError("Migration rates mismatch")

    def _get_event_names(self, events):
        # NOTE: we rely on the fact that all public fields of
        # DiscreteDemography are event lists or the migration
        # matrix.  Thus, we filter out migmatrix and all
        # magic fxns.
        return [i for i in events.__dir__() if '__' not in i
                and 'migmatrix' not in i]

    def _make_event_queues(self, events):
        """
        Take references from the input so that we can process them
        w/o affecting the input.
        """
        from collections import deque

        rv = {}
        for e in self._get_event_names(events):
            rv[e] = deque([i for i in events.__getattribute__(e)])

        return rv

    def _get_next_event_time(self, event_queues):
        t = None
        for key, value in event_queues.items():
            if len(value) > 0:
                if t is None:
                    t = value[0].when
                else:
                    t = min(t, value[0].when)
        return t

    def _current_events(self, t, event_queues, event):
        elist = []
        while len(event_queues[event]) > 0 and \
                event_queues[event][0].when == t:
            e = event_queues[event][0]
            elist.append(e)
            event_queues[event].popleft()
        return elist

    def _apply_mass_migrations(self, t, event_queues):
        for e in self._current_events(t, event_queues, 'mass_migrations'):
            if self.current_deme_sizes[e.source] == 0:
                raise ValueError(
                    "mass migration at time {} involves "
                    "empty source deme {}".format(t, e.source))
            n_from_source = np.rint(
                self.current_deme_sizes[e.source]*e.fraction).astype(int)
            if n_from_source > self.current_deme_sizes[e.source] and \
                    e.move_individuals is True:
                raise ValueError("mass migration at time {} "
                                 "moves {} individuals from "
                                 "source deme {}".format(t, n_from_source,
                                                         e.source))
            if e.move_individuals is True:
                self.current_deme_sizes[e.source] -= n_from_source
                self.current_deme_sizes[e.destination] += n_from_source
            else:  # A copy
                self.current_deme_sizes[e.destination] += n_from_source
            if e.resets_growth_rate is True:
                self.growth_rates[e.source] = fwdpy11.NOGROWTH
                self.growth_rates[e.destination] = fwdpy11.NOGROWTH
                self.growth_onset_times[e.source] = t
                self.growth_onset_times[e.destination] = t

    def _update_current_deme_sizes(self, t, event_queues):
        for e in self._current_events(t, event_queues, 'set_deme_sizes'):
            self.current_deme_sizes[e.deme] = e.new_size
            if e.resets_growth_rate is True:
                self.growth_rates[e.deme] = fwdpy11.NOGROWTH

            # Deme size has change.  So, no matter what,
            # there is a new onsite time for growth!
            self.growth_onset_times[e.deme] = t
            self.growth_initial_sizes[e.deme] = self.current_deme_sizes[e.deme]

    def _update_selfing_rates(self, t, event_queues):
        for e in self._current_events(t, event_queues, 'set_selfing_rates'):
            if self.current_deme_sizes[e.deme] == 0:
                raise ValueError("Setting selfing rate in "
                                 "extinct deme {} at "
                                 "time {}".format(e.deme, e.when))
            self.selfing_rates[e.deme] = e.S

    def _update_growth_rates(self, t, event_queues):
        for e in self._current_events(t, event_queues, 'set_growth_rates'):
            if self.current_deme_sizes[e.deme] == 0:
                raise ValueError(
                    "attempt to change growth "
                    "rate in extinct deme {} "
                    "at time {}".format(e.deme, e.when))
            self.growth_rates[e.deme] = e.G
            self.growth_onset_times[e.deme] = t
            self.growth_initial_sizes[e.deme] = self.current_deme_sizes[e.deme]

    def _update_migration_matrix(self, t, event_queues):
        for e in self._current_events(t, event_queues, 'set_migration_rates'):
            if e.deme >= 0:
                self.M[e.deme, :] = e.migrates
            else:
                self.M[:] = e.migrates.reshape(self.M.shape)

    def _apply_growth_rates(self, t, event_queues):
        next_deme_sizes = np.copy(self.current_deme_sizes)
        for i, j in enumerate(self.growth_rates):
            if j != fwdpy11.NOGROWTH:
                if self.current_deme_sizes[i] == 0:
                    raise ValueError("growth is happening "
                                     "at time {} in extinct "
                                     "deme {}".format(t, i))
                onset = self.growth_onset_times[i]
                G = self.growth_rates[i]
                Nonset = self.growth_initial_sizes[i]
                nextN = np.rint(Nonset * np.power(G, t - onset+1)).astype(int)
                if nextN <= 0:
                    nextN = 0
                    self.growth_rates[i] = fwdpy11.NOGROWTH
                    self.growth_initial_sizes[i] = 0
                    self.growth_onset_times[i] = t
                next_deme_sizes[i] = nextN

        return next_deme_sizes

    def _generate_report(self, event_queues):
        """
        Apply events in the same way as the C++
        back-end.
        """
        t = 0  # NOQA
        report = []
        t = self._get_next_event_time(event_queues)
        global_extinction = False
        while t is not None and global_extinction is False:
            self._apply_mass_migrations(t, event_queues)
            self._update_current_deme_sizes(t, event_queues)
            self._update_growth_rates(t, event_queues)
            self._update_selfing_rates(t, event_queues)
            self._update_migration_matrix(t, event_queues)
            next_deme_sizes = self._apply_growth_rates(t, event_queues)
            if next_deme_sizes.sum() == 0:
                global_extinction = True
            t = self._get_next_event_time(event_queues)
        return report

    def _process_demographic_model(self, events):
        event_queues = self._make_event_queues(events)

        report = self._generate_report(event_queues)

        return report
