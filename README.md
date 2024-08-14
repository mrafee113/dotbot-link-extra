### dotbot-link-extra

This code sucks. I dislike the original code, and I dislike my adjustments to it. It's so badly organized so much so that scaling it was more difficult than it needed to be.

TODO: rewrite the whole plugin from scratch this time.

WARNING: there's a bug that I didn't have time to address. for `perms-file`, if the file doesn't exist and this directive is run from inside the `sudo` directive, the perms file created will belong to root.

old logic as of revision [720265](https://github.com/anishathalye/dotbot/tree/720206578a8daf1e7167200e73e314fc4b8af52e):

    link:
        when dest exists && dest is symlink to not source                                              -> invalid link
        elif (dest doesn't exist || dest is not regular file/dir) && (ignore-missing || source exists) -> symlink
        elif dest is file/dir && dest is not symlink                                                   -> dest already exists
        elif dest is symlink to not source                                                             -> incorrect link
        elif source doesn't exist                                                                      -> nonexistent source
        else                                                                                           -> link exists
    
    delete:
        when (dest is symlink to not source || dest is regular file/dir) && (dest is symlink || force) -> remove dest

    when create -> create parents
    when force || relink -> delete dest
    link

new logic:

    !! note that I didn't test this thoroughly with all the variations of the vars, e.g. `relative`.

    extra options (local and defaults):
        - store-perms := true
        - perms-file  := {base-directory}/.perms.yaml
        - backup      := true
        - backup-dir  := {base-directory}/backups/
        - replace     := true
    
    link: (same as before)

    backup:
        when source exists -> backup to backup-directory
        else               ->
            backup as source (replace)
            when store-perms -> store permissions

    delete:
        when (
            dest is symlink to not source || \
            dest is regular file/dir || \
            (dest is symlink to source && !ignore-missing))
        ) && (dest is symlink || force) -> remove dest
        when (source exists && dest is regular file/dir && replace) -> remove dest
    
    store-perms:
        when source is symlink and is file -> return True
        when source does not exist or is broken symlink -> return ignore-missing
        paths = [source]
        when source is dir -> recursively add everything to paths
        store permissions, uid, and gid in perms-file

    when create -> create parents
    when dest is regular file/dir && backup -> backup
    when (!glob || doesn't have glob chars) && (!ignore-missing && source doesn't exist) -> nonexistent source
    when force || relink || replace -> delete dest
    when ignore-missing and dest is broken symlink -> continue
    when store-perms -> store-perms
    link

TODO: there should be a script that when called, fixes the ownership and permissions of files listed in the src/perms file.
    this is most useful when cloning the repo anew; since git does not store permissions (besides executable bit).
