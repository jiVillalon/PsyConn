% Standalone test: run NIFTI_NORDIC on ONE echo of sub-P5 ses-6 rest run-1
% from Octave directly, without oct2py. Captures the raw Octave error so
% we can diagnose silent crashes that oct2py does not surface.
%
% Usage (from PowerShell):
%   octave-cli --no-gui "D:/ProfessionalProyects/PsyLSD/src/octave_shims/test_nordic_standalone.m" > D:/test_nordic.log 2>&1
% Or interactive:
%   octave-cli
%   >> run("D:/ProfessionalProyects/PsyLSD/src/octave_shims/test_nordic_standalone.m")

more off;   % flush fprintf / disp immediately
pkg load signal;  % NIFTI_NORDIC uses tukeywin for the phase filter
addpath("D:/ProfessionalProyects/PsyLSD/src/external/nifti_tools");
addpath("D:/ProfessionalProyects/PsyLSD/src/octave_shims");
addpath("D:/ProfessionalProyects/PsyLSD/src/external/NORDIC_Raw");

BIDS = "D:/ProfessionalProyects/PsyLSD/data/openneuro/ds006072";
mag  = sprintf("%s/sub-P5/ses-6/func/sub-P5_ses-6_task-BOLDREST1_dir-PA_run-1_echo-1_part-mag_bold.nii.gz", BIDS);
ph   = strrep(mag, "_part-mag_", "_part-phase_");
work = fileparts(mag);
fn_out = "test_standalone_NORDIC_tmp";

fprintf("[%s] start\n", datestr(now, "HH:MM:SS"));
fprintf("mag exists:   %d\n", exist(mag,   "file") == 2);
fprintf("phase exists: %d\n", exist(ph,    "file") == 2);
fprintf("workdir:      %s\n", work);

ARG = struct();
ARG.temporal_phase       = 1;
ARG.phase_filter_width   = 10;
ARG.NORDIC               = 1;
ARG.MP                   = 0;
ARG.write_gzipped_niftis = 1;
ARG.DIROUT               = [work '/'];
ARG.noise_volume_last    = 3;
ARG.magnitude_only       = 0;

fprintf("[%s] calling NIFTI_NORDIC...\n", datestr(now, "HH:MM:SS"));

try
    NIFTI_NORDIC(mag, ph, fn_out, ARG);
    fprintf("[%s] NIFTI_NORDIC returned OK\n", datestr(now, "HH:MM:SS"));
catch err
    fprintf("[%s] NIFTI_NORDIC FAILED\n", datestr(now, "HH:MM:SS"));
    fprintf("  identifier: %s\n", err.identifier);
    fprintf("  message:    %s\n", err.message);
    if isfield(err, "stack")
        for k = 1:numel(err.stack)
            s = err.stack(k);
            fprintf("  at %s:%d (%s)\n", s.file, s.line, s.name);
        end
    end
end

fprintf("[%s] done\n", datestr(now, "HH:MM:SS"));
