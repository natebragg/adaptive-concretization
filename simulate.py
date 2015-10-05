#!/usr/bin/env python

from itertools import repeat, chain
from functools import partial
import random
from optparse import OptionParser
import sys

import numpy as np
from scipy import stats
from scipy.stats import wilcoxon

from db import PerfDB
import util

verbose = False
ttime = 0

# default-ish degrees
degrees = [16, 32, 64, 128, 512, 1024, 2048, 4096]

model = {}
sMap = {}

def sampling(data, b, d, n=1):
  res = {}
  if d not in data[b].keys(): return res
  pop = filter(lambda i: not data[b][d]["ttime"][i][0], range(len(data[b][d]["search space"])))
  try:
    pop_len = len(data[b][d]["search space"])
    #if verbose: print "Sampling from {} trials for degree {}...".format(pop_len, d)
    samp = random.sample(pop, n)
  except ValueError: # sample larger than population
    samp = list(chain.from_iterable(repeat(range(pop_len), n / pop_len))) + random.sample(range(pop_len), n % pop_len) 
  except TypeError: # single value
    samp = repeat(pop_len, n)

  res["p"] = data[b][d]["p"]
  for k in ["ttime", "search space"]:
    res[k] = map(lambda idx: data[b][d][k][idx], samp)
  #print "data: {}".format(res)
  return res


def sim_with_degree(sampler, n_cpu, s_name, d, n_runs = 0):
  ttime = 0
  found = False
  while not found and ttime <= 7200000:
    runs = sampler(d, n_cpu)
    _n_runs = 0
    _ttime = 0
    for s, t in runs["ttime"]:
      _n_runs = _n_runs + 1
      _ttime = _ttime + t
      found = found | s
      if found:
        #print "{} found a solution within {} trials".format(s_name, n_runs+_n_runs)
        _ttime = t
        break
    n_runs = n_runs + _n_runs
    ttime = ttime + _ttime

  return found, ttime

def run_async_trials(sampler, d, n, s_name):
  _soltime = 0
  _ttime = 0
  found = False
  ttime = 0
  t_runs = sampler(d, n)
  if not t_runs: return ttime, found, len(t_runs)
  if d not in model:
    model[d] = {}
    model[d]["runs"] = []
    model[d]["ttime"] = 0
    model[d]["search space"] = []
  for s, t in t_runs["ttime"]:
    model[d]["runs"].append(t)
    if found:
      if s and t < _soltime: _soltime = t
    elif s:
      _soltime = t
    found = found | s
    _ttime = _ttime + t
  if found:
    print "One of {} async trials found a solution.".format(s_name, len(t_runs["ttime"]))
    ttime = _soltime
  else:
    ttime = (_ttime / len(t_runs["ttime"]))
  model[d]["p"] = t_runs["p"]
  model[d]["search space"] = model[d]["search space"] + t_runs["search space"]
  return ttime, found, len(t_runs)

def test_runs(sampler, n_cpu, s_name, ds):
  ttime = 0
  found = False
  n_runs = 0
  for d in ds:
    if d not in model:
      model[d] = {}
      model[d]["runs"] = []
      model[d]["ttime"] = 0
      model[d]["search space"] = []
    l = len(model[d]["runs"])
    if l >= n_cpu/2: break
    #if verbose: print "{} trials exist! Run {} trials more!".format(l, n_cpu/2 - l)
    t_runs = sampler(d, n_cpu/2 - l)

    _n_runs = 0
    _ttime = 0
    if not t_runs: break
    for s, t in t_runs["ttime"]:
      model[d]["runs"].append(t)
      _n_runs = _n_runs + 1
      _ttime = _ttime + t
      found = found | s
      if found:
        print "{} found a solution while {} test runs".format(s_name, n_runs+_n_runs)
        _ttime = t
        break

    n_runs = n_runs + _n_runs
    model[d]["ttime"] = model[d]["ttime"] + _ttime
    model[d]["p"] = t_runs["p"]
    model[d]["search space"] = model[d]["search space"] + t_runs["search space"]

    ttime = ttime + _ttime
    if found: break

  return ttime, found, n_runs


def strategy_fixed(d, sampler, n_cpu):
  return sim_with_degree(sampler, n_cpu, "strategy_fixed_()".format(d), d)


def strategy_random(sampler, n_cpu):
  # pick a degree randomly
  d = random.choice(degrees)
  #if verbose: print "strategy_random, pick degree: {}".format(d)

  return sim_with_degree(sampler, n_cpu, "strategy_random", d)


def strategy_time(f, msg, sampler, n_cpu):
  ttime, found, n_runs = test_runs(sampler, n_cpu, msg, degrees)

  # resampling with likelihood degree
  if not found:
    est = []
    ds = []
    for d in model:
      est.append(model[d]["ttime"])
      ds.append(d)
    idx = est.index(f(est))
    d = ds[idx]
    if verbose: print "{}, pick degree: {}".format(msg, d)

    ttime = ttime + sim_with_degree(sampler, n_cpu, msg, d, n_runs)

  return ttime





def strategy_wilcoxon(sampler, n_cpu, pVal=0.17, sampleBnd=0):
  if sampleBnd == 0: sampleBnd = max(8, n_cpu/2) * 3
  
  def comp_dist(d):
    res = []
    if d not in model.keys(): 
      #if verbose: print "degree {} does not exist in {}".format(d, model.keys())
      return res
    for i in xrange(len(model[d]["runs"])):
      t = model[d]["runs"][i]
      p = model[d]["search space"][i]
      if p == 0:
        p = 10000
      res.append(t * p)
    return res

  def sampleRequested(degree):
    if degree in sMap:
      return sMap[degree];
    else:
      sMap[degree] = 0
    return sMap[degree]

  def sample(sampler, degree, s_name):
    prev = sampleRequested(degree)
    sMap[degree] = prev + n_cpu/2
    _ttime, _found, _n_runs = run_async_trials(sampler, degree, n_cpu/2, s_name)
    return _ttime, _found, _n_runs

  def compare_async(d1, d2):
    print "comparing {} and {}.".format(d1, d2)
    len_a = 0
    len_b = 0
    req_a = 0
    req_b = 0
    _found = False
    _n_runs = 0
    global ttime 
    while (len_a < sampleBnd or len_b < sampleBnd):
      dist_a = comp_dist(d1)
      dist_b = comp_dist(d2)
      len_a = len(dist_a)
      len_b = len(dist_b)
      if _found:
        _pvalue = 0
      elif not (dist_a and dist_b): _pvalue = 0
      else:
        if len(dist_a) != len(dist_b):
          print "length mismatch: {} vs. {}".format(len(dist_a), len(dist_b))
          shorter = min(len(dist_a), len(dist_b))
          dist_a = dist_a[:shorter]
          dist_b = dist_b[:shorter]
        _rank_sum, _pvalue = wilcoxon(dist_a, dist_b)
        print "pvalue is: {}".format(_pvalue)
        if _pvalue < pVal: break
        elif len(dist_a) >= sampleBnd and len(dist_b) >= sampleBnd: break
      req_a = sampleRequested(d1)
      req_b = sampleRequested(d2)
      if (req_a >= sampleBnd and req_b >= sampleBnd): break
      if (req_a <= req_b and req_a < sampleBnd): 
        _ttime, _found, _n_runs = sample(sampler, d1, "strategy_wilcoxon")
        ttime = ttime + _ttime
        len_a = len_a + _n_runs
        req_a = sampleBnd if _n_runs == 0 else req_a + _n_runs
      if (req_b <= req_a and req_b < sampleBnd): 
        _ttime, _found, _n_runs = sample(sampler, d2, "strategy_wilcoxon")
        ttime = ttime + _ttime
        len_b = len_b + _n_runs
        req_b = sampleBnd if _n_runs == 0 else req_b + _n_runs

    return dist_a, dist_b, _found, _n_runs, _pvalue

  def compare_single(d1, d2):
    print "Comparing degrees {} and {}".format(d1, d2)
    _ttime, _found, _n_runs = test_runs(sampler, n_cpu, "strategy_wilcoxon", [d1, d2])
    global ttime 
    ttime = ttime + _ttime
    dist_d1 = comp_dist(d1)
    dist_d2 = comp_dist(d2)
    if _found:
      _pvalue = 0
    elif not (dist_d1 and dist_d2): _pvalue = 0
    elif len(dist_d1) != len(dist_d2):
      print "length mismatch: {} vs. {}".format(len(dist_d1), len(dist_d2))
      _pvalue = 0
    else: _rank_sum, _pvalue = wilcoxon(dist_d1, dist_d2)
    return dist_d1, dist_d2, _found, _n_runs, _pvalue

  def binary_search(degree_l, degree_h, cmpr):
    if degree_l == degree_h: return degree_l
    dist_l, dist_h, found, n_runs, pvalue = cmpr(degree_l, degree_h)
    if pvalue == 0: return [degree_l, degree_h]
    elif (degree_h - degree_l <= degrees[0]):
      mean_l = np.mean(dist_l)
      mean_h = np.mean(dist_h)
      return degree_l if mean_l <= mean_h else degree_h
    else:
      degree_m = (degree_l + degree_h) / 2
      dist_dl, dist_dm, found, n_runs, pvalue = cmpr(degree_l, degree_m)
      if pvalue <= pVal: # the median diff. is significatly different
        if np.mean(dist_dl) < np.mean(dist_dm):
          return binary_search(degree_l, degree_m, cmpr)
        else:
          return binary_search(degree_m, degree_h, cmpr)
      else: return degree_m
  
  pivots = [0, 1]

  d = None
  found = False
  fixed = False
  n_runs = 0
  cmpr = compare_async
  while not found and not fixed and pivots[1] < len(degrees):
    fixed = True
    ds = [ degrees[pivot] for pivot in pivots ]
    d1, d2 = ds
    dist_d1, dist_d2, found, n_runs, pvalue = cmpr(d1, d2)

    if found:
      return found, ttime
    elif not dist_d1:
      pivots[0] = pivots[0] + 1
      pivots[1] = pivots[1] + 1
      fixed = False
    elif not dist_d2:
      pivots[1] = pivots[1] + 1
      fixed = False
    elif pvalue <= pVal: # the median diff. is significatly different
      if np.mean(dist_d1) < np.mean(dist_d2):
        # left one is better, climbing done
        break
      else:
        pivots[0] = pivots[0] + 1
        pivots[1] = pivots[1] + 1
        fixed = False
    else: # i.e., can't differentiate two degrees
      pivots[1] = pivots[1] + 1
      fixed = False

  if pivots[1] == len(degrees): pivots[1] = pivots[1] - 1

  # binary search now
  dl = degrees[pivots[0]]
  dh = degrees[pivots[1]]
  d = binary_search(dl, dh, cmpr)
  global ttime 
  if verbose: print "strategy_wilcoxon, pick degree: {}".format(d)
  if not found and type(d) is int and ttime <= 7200000:
    found, _ttime = sim_with_degree(sampler, n_cpu, "strategy_wilcoxon", d, n_runs)
    ttime = ttime + _ttime

  return d, ttime


def simulate(data, n_cpu, strategy, b):
  global degrees
  global model
  global sMap
  #degrees = sorted(data[b].keys())
  sampler = partial(sampling, data, b)
  res = []
  dgrs = {}
  ranges = []
  for i in xrange(301):
    model = {}
    sMap = {}
    found = False
    _d, _ttime = strategy(sampler, n_cpu)
    res.append(_ttime)
    if type(_d) == int:
      if _d in dgrs: dgrs[_d] = dgrs[_d] + 1
      else: dgrs[_d] = 1
    else: 
      ranges.append(_d)
      low_choice = ((_d[0]-1) / degrees[0] + 1) * degrees[0]
      high_choice = _d[1] / degrees[0] * degrees[0]
      choices = range(low_choice, high_choice+1, degrees[0])
      for i in choices:
        if i in dgrs: dgrs[i] = dgrs[i] + (1 / (len(choices) * 1.0))
        else: dgrs[i] = 1 / (len(choices) * 1.0)
  print "{} simulations ({}%) found fixed degrees!".format(301 - len(ranges), (301-len(ranges))/3.01)
  #for [low, high] in ranges:
  #  for dgr in dgrs:
  #    if low <= dgr and dgr <= high: dgrs[dgr] = dgrs[dgr] + 1
  for d in sorted(dgrs.keys()):
    print "degree {}: {} times".format(d, dgrs[d])
  return res


def main():
  parser = OptionParser(usage="usage: %prog [options]")
  parser.add_option("--user",
    action="store", dest="user", default="sketchperf",
    help="user name for database")
  parser.add_option("--db",
    action="store", dest="db", default="concretization",
    help="database name")
  parser.add_option("-e", "--eid",
    action="store", dest="eid", type="int", default=11,
    help="experiment id")
  parser.add_option("-d", "--dir",
    action="store", dest="data_dir", default="data",
    help="output folder")
  parser.add_option("-b", "--benchmark",
    action="append", dest="benchmarks", default=[],
    help="benchmark(s) of interest")
  parser.add_option("--all",
    action="store_true", dest="all_strategies", default=False,
    help="simulate *all* modeled strategies")
  parser.add_option("-v", "--verbose",
    action="store_true", dest="verbose", default=False,
    help="verbosely print out simulation data")

  (opt, args) = parser.parse_args()

  global verbose
  verbose = opt.verbose

  db = PerfDB(opt.user, opt.db)
  db.drawing = True
  db.detail_space = True
  db.calc_stat(opt.benchmarks, True, opt.eid)
  data = db.raw_data

  merged = util.merge_succ_fail(data, 1000)

  n_cpu = 32
  _simulate = partial(simulate, merged, n_cpu)
  simulators = {}
  simulators["wilcoxon"] = partial(_simulate, strategy_wilcoxon)
  if opt.all_strategies:
    simulators["random"] = partial(_simulate, strategy_random)
    strategy_min_time = partial(strategy_time, min, "strategy_min_time")
    strategy_max_time = partial(strategy_time, max, "strategy_max_time")
    simulators["min(time)"] = partial(_simulate, strategy_min_time)
    simulators["max(time)"] = partial(_simulate, strategy_max_time)

  for b in merged:
    print "\n=== benchmark: {} ===".format(b)

    _simulators = simulators.copy()
    if opt.all_strategies:
      degrees = sorted(merged[b].keys())
      for d in degrees:
        strategy_fixed_d = partial(strategy_fixed, d)
        _simulators["fixed({})".format(d)] = partial(_simulate, strategy_fixed_d)

    for s in sorted(_simulators.keys()):
      print "Simulating strategy {}...".format(s)
      res = _simulators[s](b)
      print "{} simulations done.".format(len(res))
      s_q = " | ".join(map(str, util.calc_percentile(res)))
      print "{} : {} ({}) [ {} ]".format(s, np.mean(res), np.var(res), s_q)


if __name__ == "__main__":
  sys.exit(main())


