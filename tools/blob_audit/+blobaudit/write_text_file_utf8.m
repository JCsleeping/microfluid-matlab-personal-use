function write_text_file_utf8(path, text)
% WRITE_TEXT_FILE_UTF8  Write text using UTF-8 where supported.

    fid = fopen(path, 'w', 'n', 'UTF-8');
    if fid < 0
        fid = fopen(path, 'w');
    end
    if fid < 0
        error('write_text_file_utf8:openFailed', 'Could not open %s for writing.', path);
    end
    cleaner = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, '%s', text);
end
