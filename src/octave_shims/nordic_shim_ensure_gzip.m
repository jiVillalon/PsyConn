function nordic_shim_ensure_gzip()
    % Ensure the "gzip" binary that Octave's gunzip()/gzip() shell out to
    % is resolvable via PATH. On Windows launched from a shell that does
    % not inherit Octave's mingw PATH (e.g., octave-cli.exe from a raw
    % PowerShell), gzip is absent and gunzip fails with:
    %   unpack: unarchiving program exited with status: 1
    %   "gzip" no se reconoce como un comando ...
    % This helper probes OCTAVE_HOME for the bundled gzip.exe and
    % prepends its directory to PATH. Idempotent via a persistent flag.
    persistent done
    if ~isempty(done)
        return
    end

    if ~ispc()
        done = true;
        return
    end

    [rc, ~] = system('gzip --version >nul 2>&1');
    if rc == 0
        done = true;
        return
    end

    try
        octroot = OCTAVE_HOME();
    catch
        octroot = getenv('OCTAVE_HOME');
    end
    if isempty(octroot)
        warning('nordic_shim_ensure_gzip: OCTAVE_HOME not resolvable');
        done = true;
        return
    end

    % OCTAVE_HOME() may return either the install root
    % (C:\Program Files\GNU Octave\Octave-11.1.0) or the mingw64 subdir
    % (C:\Program Files\GNU Octave\Octave-11.1.0\mingw64). Probe both.
    octparent = fileparts(octroot);
    candidates = { ...
        fullfile(octroot,   'usr', 'bin'), ...
        fullfile(octroot,   'mingw64', 'usr', 'bin'), ...
        fullfile(octroot,   'mingw64', 'bin'), ...
        fullfile(octroot,   'bin'), ...
        fullfile(octparent, 'usr', 'bin'), ...
        fullfile(octparent, 'mingw64', 'usr', 'bin'), ...
        fullfile(octparent, 'mingw64', 'bin'), ...
        fullfile(octparent, 'bin') ...
    };

    for k = 1:numel(candidates)
        gz = fullfile(candidates{k}, 'gzip.exe');
        if exist(gz, 'file') == 2
            setenv('PATH', [candidates{k} pathsep() getenv('PATH')]);
            done = true;
            return
        end
    end

    warning('nordic_shim_ensure_gzip: gzip.exe not found under %s', octroot);
    done = true;
end
