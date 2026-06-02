function niftiwrite(img, filename, varargin)
    % MATLAB-compatible shim for GNU Octave, wrapping Jimmy Shen's
    % save_untouch_nii. Accepts the four call shapes NIFTI_NORDIC.m uses:
    %   niftiwrite(img, path)
    %   niftiwrite(img, path, info)
    %   niftiwrite(img, path, 'Compressed', true)           % g-factor
    %   niftiwrite(img, path, info, 'Compressed', true)
    %
    % save_untouch_nii cannot emit .nii.gz directly in Octave, so when
    % Compressed=true the shim writes a plain .nii and then gzips it with
    % Octave's core gzip() (removing the plain file). If info carries the
    % original Jimmy Shen nii struct in info.raw (set by the niftiinfo
    % shim), it is reused so sform/qform/pixdim/intent survive intact; dim
    % and datatype are updated to match the output array.

    nordic_shim_ensure_gzip();

    info = [];
    nv_start = 1;
    if ~isempty(varargin) && isstruct(varargin{1})
        info = varargin{1};
        nv_start = 2;
    end

    compressed = false;
    for k = nv_start:2:numel(varargin)
        if k+1 > numel(varargin), break; end
        if strcmpi(varargin{k}, 'Compressed')
            compressed = logical(varargin{k+1});
        end
    end

    if ~isempty(info) && isfield(info, 'raw') && isstruct(info.raw)
        nii = info.raw;
    else
        nii = make_nii(img);
    end
    nii.img = img;

    s = size(img);
    ndim = numel(s);
    nii.hdr.dime.dim(1) = ndim;
    nii.hdr.dime.dim(2:1+ndim) = s;
    if ndim < 7
        nii.hdr.dime.dim(2+ndim:8) = 1;
    end

    [dcode, bpp] = nordic_shim_nifti_datatype(class(img));
    nii.hdr.dime.datatype = dcode;
    nii.hdr.dime.bitpix   = bpp;

    % Resolve final output path.
    if compressed
        if ~nordic_shim_endswith(filename, '.nii.gz')
            if nordic_shim_endswith(filename, '.nii')
                filename = [filename '.gz'];
            else
                filename = [filename '.nii.gz'];
            end
        end
    else
        if ~nordic_shim_endswith(filename, '.nii') && ...
           ~nordic_shim_endswith(filename, '.nii.gz')
            filename = [filename '.nii'];
        end
    end

    if compressed
        % Write plain .nii first, then gzip it (Octave path).
        plain = filename(1:end-3);  % strip '.gz'
        if exist(plain, 'file'),    delete(plain);    end
        if exist(filename, 'file'), delete(filename); end
        save_untouch_nii(nii, plain);
        gzip(plain);
        delete(plain);
    else
        if exist(filename, 'file'), delete(filename); end
        save_untouch_nii(nii, filename);
    end
end


function tf = nordic_shim_endswith(s, suf)
    n = length(suf);
    tf = length(s) >= n && strcmp(s(end-n+1:end), suf);
end


function [code, bpp] = nordic_shim_nifti_datatype(c)
    switch lower(c)
        case 'uint8',   code =    2; bpp =  8;
        case 'int16',   code =    4; bpp = 16;
        case 'int32',   code =    8; bpp = 32;
        case 'single',  code =   16; bpp = 32;
        case 'double',  code =   64; bpp = 64;
        case 'int8',    code =  256; bpp =  8;
        case 'uint16',  code =  512; bpp = 16;
        case 'uint32',  code =  768; bpp = 32;
        case 'int64',   code = 1024; bpp = 64;
        case 'uint64',  code = 1280; bpp = 64;
        otherwise
            error('niftiwrite shim: unsupported class %s', c);
    end
end
