# first line: 19
@memory.cache(ignore=['noisy', 'seed'])
def run_sketch(path, main, iteration, noisy=False, extra=None,
               mem=None, seed=None, par=False, ac=False,
               degree=None, timeout=None, ntimes=None):
    opt = lambda cond, *args: list(args) if cond else []
    fe_timeout_supported = '--fe-timeout' in subprocess.getoutput('sketch --help')
    with tempfile.TemporaryDirectory() as tmp_dir:
        cmd = ' '.join([            'sketch', main,
                                    '--fe-inc', path,
                                    '--fe-tempdir', tmp_dir,
                                    '--fe-keep-tmp',
                                    '-V', '5']
        + opt(mem,                  '--slv-mem-limit', str(mem))
        + opt(seed,                 '--slv-seed', str(seed))
        + opt(par,                  '--slv-parallel')
        + opt(ac,                   '--slv-randassign')
        + opt(degree,               '--slv-randdegree', str(degree))
        + opt(timeout and
              fe_timeout_supported, '--fe-timeout', str(timeout))
        + opt(timeout,              '--slv-timeout', str(timeout))
        + opt(ntimes,               '--slv-ntimes', str(ntimes))
        + opt('sygus' in path,      '--fe-def', 'BND=5',
                                    '--bnd-unroll-amnt', '64')
        + opt(extra,                *(extra or []))
        )
        before = datetime.datetime.now()
        output = subprocess.getoutput(cmd)
        after = datetime.datetime.now()
        if noisy:
            print('%s, iteration %d, runtime: %s' % (main, iteration, str(after - before)))
        return dict(ChainMap({
            'cmd': cmd,
            'before': before,
            'after': after,
            'stdout': output,
        }, *sketch_temp_files(tmp_dir)))
