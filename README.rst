.. image:: https://travis-ci.com/focusate/git-trunk.svg?branch=master
    :target: https://travis-ci.com/focusate/git-trunk

Git Trunk based workflow
########################

Adds git-trunk commands that automates some common git procedures.

Usage: :code:`git trunk <command>`

Possible commands:

* :code:`init`: initialize trunk configuration to be used for other commands.
* :code:`start`: create new branch specifying custom name or use patterns to fetch/filter remote branches. First match is used to create local branch.
* :code:`finish`: finish active branch by merging it to trunk (then remove it).
* :code:`release`: create tag with new release version.
* :code:`refresh`: update trunk branch and rebase it on active branch.
* :code:`squash`: squash commits on active branch.

Code was tested using :code:`git version 2.25.1`.

Source code in:

* `github <https://github.com/focusate/git-trunk/>`_.
* `pypi <https://pypi.org/project/git_trunk/>`_.

Quick Start
===========

For easier use, commands should be called when git repository is your working directory. If you need to call outside working directory, you can use :code:`--repo-path` argument, where you specify for which repository it should be called.

To know which commands are available, use :code:`git trunk -h`

To know what arguments are available and what they do for each command, use :code:`git trunk <command> -h` or :code:`git trunk <command> --help`

Remote used is identified by your current branch tracking branch remote. If your current branch does not have tracking branch, then trunk branch tracking branch is checked. If trunk branch does not have tracking branch set, then it is assumed no remote is used for :code:`git-trunk` workflow.

Submodules
==========

All possible commands can be used same way as on main superproject repository. Note configuration is still saved on main superproject repository config (submodules do not have git config file), but it is separated by including submodule relative path on sections. E.g. main repository section is named :code:`[trunk]`, where in submodule case, it is named :code:`[trunk "relpath/to/submodule"]`.

init
----

:code:`init` command is used to initialize git trunk configuration that is later reused for other commands. usually it is meant to be called once, where you specify options to set on configuration. Configuration is saved on your repository inside :code:`.git/config` file. Trunk sections are named :code:`trunk`.

When using :code:`init` command, by default it runs in "interactive" mode, where you have to confirm default option values or enter new ones. If you want to specify all options without a prompt, use :code:`--no-confirm` flag. With this flag, you can specify other argument and it will set without asking you to confirm it.

If you need to change configuration, you can just call :code:`init` command again by specifying options you want to change. Options not specified, will be assumed that old values must be kept.

start
-----

:code:`start` command is used to create new branch locally.

Branch that is created, uses your :code:`trunk` branch as a fork. :code:`trunk` branch is always rebased from remote :code:`trunk` before creating new branch (if of course remote is used).

When branch is created using :code:`start` command, by default it will also try to set upstream for it. To not set upstream, use :code:`--no-set-upstream` flag when running :code:`start` command.

If you need to create new branch that is not already on remote, you can use :code:`--name` argument. It will simply try to create new branch (given it does not exist already) forking from your trunk branch.

If you use system where branches are created on remote automatically (like tasks), you can configure :code:`git-trunk` to fetch specific branches only that are meant for you. :code:`start` command will try to fetch the first one (naturally sorting branch names) from remotely existing branches you filtered. If remote branch is already used as tracking branch for existing local branch, such branch is ignored and not used in automatic branch creation.

There are two ways to filter (can be combined):

* First one is by using :code:`fetchbranchpattern` option. By default it fetches all available branches from your remote. To limit what is fetched, with :code:`init` command, for example you can set :code:`*-my` value for argument :code:`--fetch-branch-pattern`. With such pattern, it will only fetch branches which names end with :code:`-my` part. Pattern uses git `refspec <https://git-scm.com/book/en/v2/Git-Internals-The-Refspec>`_. With :code:`init` command, you can change :code:`asterisk` part, but skeleton remains the same: :code:`refs/heads/<pattern>:refs/remotes/<remote>/<pattern>`
* Second can be specified every time you want to create new branch. For that you use :code:`--pattern` argument when calling :code:`git trunk start` command. Here you specify :code:`regex` pattern to further filter branches. This filtering option is used after fetched branches are filtered by refpsec pattern.

finish
------

:code:`finish` command is used to finish your temporary branch. In usual case, it is merged into trunk branch, pushed remotely and then remote respective branch is removed alongside local copy.

Currently the only exception is if you use branch that has :code:`release` prefix (:code:`init` command argument is :code:`--release-branch-prefix`). In this case such branch is recognized as release branch. When such branch is finished, it is only deleted, but not meged back into trunk. The reason is that release branches usually should not be merged into trunk.

Branches by default will be merged with :code:`--ff-only` flag. You can change to :code:`--no-ff` flag with :code:`init` command.

release
-------

:code:`release` command is used to create release tag.

By default version is created using current latest commit on a branch you are on. But it is possible to use specific reference to tag on (with :code:`--ref` argument).

Also release will be cancelled if there are no new changes after latest tag was created.

Currently there are two possible ways to manage versions:

* Generic versioning. With generic, you need to manually specify new version every time. For that you use :code:`--version` argument, where you enter new version.
* Semver versioning, which uses python :code:`semver` module as a base to manage version bumping. By default :code:`minor` part is used, but with :code:`--part` argument, you can specify other parts :code:`semver` module currently supports.

It is also possible to specify prefix for version. If prefix is used (it is set with :code:`init` command), custom version must be specified without prefix, so prefix would not be "duplicated".

Tag default message uses default template, where header line is version name and body is filled with abbreviated commits and their header lines being tagged. By default, tag message is opened for editing before being saved. Can be disabled if needed.

refresh
-------

:code:`refresh` command is used to update your current branch with new changes from trunk. It can also be used on trunk branch itself.

When you are on working branch, and :code:`refresh` command is called, your changes are stashed, then branch is changed to trunk, which then is rebased with its tracking branch (if it has upstream). Then branch is changed back to your working one, new trunk changes rebased on your working branch and stashed changes applied (if there were any).

Some other :code:`git-trunk` commands use refresh command internally to update code before executing command specific actions.

If there are conflicts during refresh, command execution stops and conflicts must be resolved (if stashes were applied, dont forget to reapply them after solving conflicts).

squash
------

:code:`squash` command is used to squash multiple commits. Squash can't be done on trunk branch.

Before initiating squash itself, branch is refreshed with newest trunk branch changes, to make sure branch is up to date.

By default it tries to squash all ahead trunk commits into first one. It is possible to specify how many commits to squash with :code:`--count` argument. Value cant be greater than maximum possible commits to squash on that branch (or actually default count that is used).

By default squash message generated is to concatenate all commit messages (including commit other commits are being squashed into). It is also possible to specify custom commit message, which replaces default message. It is also possible to not specify any message (but then edit mode must be enabled to enter one manually).

By default squash message edit is enabled, which allows to edit tag message before it is saved. Can be disabled if needed.

|

*Contributors*

* Andrius Laukavičius (Focusate)
