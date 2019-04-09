from collections import ChainMap
import subprocess
import tempfile
import joblib
import datetime
import os
import re

memory = joblib.Memory('data', compress=9, verbose=0)

def scrape(s, regex):
    tre = re.compile(regex)
    result = []
    for line in s.splitlines():
        m = tre.match(line)
        if m:
            result.append(m.group(1))
    return result

def cpu_time(s):
    ts = scrape(s, '^.*elapsed time.*-> (.*)')
    if ts:
        return sum(map(float, ts))
    else:
        ts = scrape(s, '^Total time = (.*)')
        return sum(map(lambda t: int(t)/1000.0, ts) if ts else [])

def successful(s):
    return any(map(lambda b: b in ['true', 'True'], scrape(s, '.*successful.*-> (.*)') or []))

def exit_codes(s):
    return set(map(int, scrape(s, '^\\[SATBackend\\] Solver exit value: ([0-9]+)')))

def sketch_temp_files(dir):
    for path, _, files in os.walk(dir):
        for fn in files:
            if os.path.splitext(fn)[1] != '.com':
                with open(os.path.join(path, fn)) as fd:
                    yield {fn: fd.read()}

def getoutput(cmd, timeout):
    """Exactly like subprocess.getoutput, except with a timeout."""
    with subprocess.Popen(cmd, universal_newlines=True,
                          stderr=subprocess.STDOUT,
                          stdout=subprocess.PIPE) as process:
        try:
            stdout, = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                stdout, = process.communicate(timeout=1)
            except subprocess.TimeoutExpired:
                # Fragile; see CPython issues 30154 and 26534
                if process.stdout and process._fileobj2output:
                    stdout = process._translate_newlines(
                                b''.join(process._fileobj2output[process.stdout]),
                                process.stdout.encoding, process.stdout.errors)
        except:
            process.kill()
            process.wait()
            raise
    if stdout[-1:] == '\n':
        stdout = stdout[:-1]
    return stdout

# To force refresh, instead of run_sketch(...),
# use run_sketch.call(...)[0]
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
