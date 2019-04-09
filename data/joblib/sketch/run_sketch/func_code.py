# first line: 55
@memory.cache(ignore=['sketch_home', 'sketch_path', 'noisy', 'seed', 'timeout'])
def run_sketch(sketch_version, sketch_home, sketch_path,
               path, main, iteration, noisy=False, extra=None,
               mem=None, seed=None, par=False, ac=False,
               degree=None, timeout=None, ntimes=None):
    os.environ['SKETCH_HOME'] = sketch_home
    sketch = os.path.join(sketch_path, 'sketch')
    opt = lambda cond, *args: list(args) if cond else []
    fe_timeout_supported = '--fe-timeout' in subprocess.getoutput(sketch + ' --help')
    with tempfile.TemporaryDirectory() as tmp_dir:
        cmd = ([                    sketch, main,
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
        output = getoutput(cmd, (timeout + 1) * 60) # timeout in minutes; give it 1 extra to timeout on its own.
        after = datetime.datetime.now()
        if noisy:
            print('sketch %s: %s, iteration %d, runtime: %s' % (sketch_version, main, iteration, str(after - before)))
        return dict(ChainMap({
            'cmd': ' '.join(cmd),
            'before': before,
            'after': after,
            'stdout': output,
            'successful': successful(output) or 0 in exit_codes(output),
            'cpu_time': cpu_time(output),
        }, *sketch_temp_files(tmp_dir)))
