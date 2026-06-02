function data = niftiread(filename)
    % MATLAB-compatible shim for GNU Octave.
    % Wraps Jimmy Shen's "Tools for NIfTI and ANALYZE image" (FileExchange
    % #8797). Jimmy Shen's load_untouch_nii cannot read .nii.gz in Octave
    % (it expects MATLAB's Java-backed gunzip), so the shim transparently
    % decompresses to a temp .nii first. See PsiloConn_1.0.qmd
    % §sec-nordic-octave-shims.
    nordic_shim_ensure_gzip();
    filename = nordic_shim_resolve_path(filename);
    [local, tmpdir] = nordic_shim_gunzip_if_needed(filename);
    cleanup = onCleanup(@() nordic_shim_rmdir_safe(tmpdir));
    nii = load_untouch_nii(local);
    data = nii.img;
end

function p = nordic_shim_resolve_path(p)
    if exist(p, 'file')
        return
    end
    for suf = {'.gz', '.nii', '.nii.gz'}
        q = [p suf{1}];
        if exist(q, 'file')
            p = q;
            return
        end
    end
end

function [local_path, tmpdir] = nordic_shim_gunzip_if_needed(p)
    tmpdir = '';
    local_path = p;
    if length(p) >= 3 && strcmp(p(end-2:end), '.gz')
        tmpdir = tempname();
        mkdir(tmpdir);
        gunzip(p, tmpdir);
        [~, base, ext] = fileparts(p(1:end-3));
        local_path = fullfile(tmpdir, [base ext]);
    end
end

function nordic_shim_rmdir_safe(d)
    if ~isempty(d) && exist(d, 'dir')
        try
            rmdir(d, 's');
        catch
        end
    end
end
