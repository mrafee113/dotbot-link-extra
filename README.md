### dotbot-link-extra

old logic:

    as of revision [720265](https://github.com/anishathalye/dotbot/tree/720206578a8daf1e7167200e73e314fc4b8af52e)

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
        - store-perms := false
        - perms-file  := {base-directory}/.perms.yaml
        - backup      := false
        - backup-dir  := {base-directory}/backups/
    
    link: (same as before)

    backup:
        when source exists -> backup to backup-directory
        else               ->
            backup as source
            when store-perms -> store permissions

    delete:
        when (
            dest is symlink to not source || \
            dest is regular file/dir || \
            (dest is symlink to source && !ignore-missing))
        ) && (dest is symlink || force) -> remove dest

    when create -> create parents
    when dest is regular file/dir && backup -> backup
    when (!glob || doesn't have glob chars) && (!ignore-missing && source doesn't exist) -> nonexistent source
    when force || relink -> delete dest
    link

TODO: there should be a script that when called, fixes the ownership and permissions of files listed in the src/perms file.
    this is most useful when cloning the repo anew; since git does not store permissions (besides executable bit).
