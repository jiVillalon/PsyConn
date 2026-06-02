function info = niftiinfo(filename)
    % MATLAB-compatible shim for GNU Octave. Pre-decompresses .nii.gz to
    % a temp .nii (Jimmy Shen's toolbox can't gunzip in Octave), reads via
    % load_untouch_nii, and returns a struct exposing the fields
    % NIFTI_NORDIC.m consumes (.Datatype) plus .raw for round-trip to the
    % niftiwrite shim.
    nordic_shim_ensure_gzip();
    filename = nordic_shim_resolve_path(filename);
    [local, tmpdir] = nordic_shim_gunzip_if_needed(filename);
    cleanup = onCleanup(@() nordic_shim_rmdir_safe(tmpdir));
    nii = load_untouch_nii(local);
    info.Filename        = filename;
    info.ImageSize       = size(nii.img);
    info.Datatype        = class(nii.img);
    info.PixelDimensions = nii.hdr.dime.pixdim(2:1+ndims(nii.img));
    info.raw             = nii;
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
