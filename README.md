# Github Android App Search tool

This script facilitates finding Android apps on Github and matching them with
entries on Google Play. Information from GitHub and Google Play get combined to
build a connected dataset of open-source Apps, their source code, and version
control data.

Meta-data of all Android apps is stored in a Neo4j graph database and snapshots
of all GitHub repositories are cloned to a local Gitlab instance.


## Background and motivation

The idea is to create a dataset of open-source Android applications which can
serve as a base for research. Data on Android apps is spread out over multiple
source and finding a large number real-world applications with access to source
code requires combining these different databases.


## Requirements

Some data preparation is necessary for commands in this script to run.
An initial list of package names and GitHub repositories is required because
GitHub API limitations prevent retrieving all search results, even if
stratified by byte-granular filesize.
A good way to get such data is
[Google BigQuery](https://cloud.google.com/bigquery/public-data/github).
All steps of the process are detailed in
[doc/app-selection](doc/app-selection.md).


## Results: Graph database and Git repository snapshots

The results of the data collection process are a list of 8,431 open-source
Android apps with metadata from their Google Play pages and 8,216 GitHub
repositories with the source code of those apps.

All this information is made available in two ways:

 1. A [Neo4j](https://neo4j.com) graph database containing metadata of
    repositories and apps and highlevel information on commit history of all
    repositories.
 2. Snapshots of all GitHub repositories in the dataset cloned to a local
    Gitlab instance.

![Schema of the graph database](doc/img/dbstructure.png)

All properties of `GooglePlayPage` nodes and of `GitHubRepository` nodes are
listed in [doc/node-properties.md](doc/node-properties.md)

We published Docker images for the
[Neo4j graph database](https://hub.docker.com/r/af60f75b/neo4j_open_source_android_apps)
and the Gitlab instance (TBA; the total size of 136 GB is too large for Docker
Hub)).


## Installation

Clone the repository:

```
git clone https://github.com/S2-group/android-app-search
```

Create a virtual environment for `python3`:

```
cd android-app-search/
virtualenv --python=python3 env
```

Activate environment and install requirements:
```
source env/bin/activate
pip install --requirement requirements.txt
```

It is recommended to use an
[authentication token for Github API](https://github.com/blog/1509-personal-api-tokens).
Set it as environment variable `GITHUB_AUTH_TOKEN`:
```
export GITHUB_AUTH_TOKEN="1234abcd...xyz"
```

For step `get_play_data`
[node-google-play-cli](https://github.com/dweinstein/node-google-play-cli)
needs to be installed and configured.


## Usage

Execute `gh_android_apps` to see all sub-commands.
```
./gh_android_apps.py
```

Get more information on each sub-command and its options by appending `-h` or
`--help`. For example:
```
./gh_android_apps.py verify_play_link --help
```

This is the full help output with descriptions of all subcommands.

```
usage: gh_android_apps.py [-h] [--log LOG] [-v] [-q]
                          {verify_play_link,get_play_data,get_repo_data,match_packages,get_gradle_files,add_gradle_info,clone,draw_commits,mirror_empty_repos,consolidate_data,store_repo_data,store_in_neo4j,play_category}
                          ...

Collect data on Android apps on Github.

Combine information from Github and Google Play to find open source Android
apps. Commonly used meta data is parsed into a graph database.

Reads environment variable GITHUB_AUTH_TOKEN to use for authentication with
Github if available. Authenticated requests have higher rate limits.

This script executes several of the interdependent steps as sub-commands. Use
the --help option on a sub-command to learn more about it.

positional arguments:
  {verify_play_link,get_play_data,get_repo_data,match_packages,get_gradle_files,add_gradle_info,clone,draw_commits,mirror_empty_repos,consolidate_data,store_repo_data,store_in_neo4j,play_category}
    verify_play_link    Filter out package names not available in Google Play.
                        For each package name in input, check if package name
                        is available in Google Play. If so, print package name
                        to output. Input and output have each package name on
                        a separate lines. Use -h or --help for more
                        information.
    get_play_data       Download package meta data from Google Play. For each
                        package name in input, use node-google-play-cli to
                        fetch meta data from Google Play and store resulting
                        JSON in out directory. Input expects each package name
                        on a separate line. Output JSON files are stored in
                        <outdir>/<package_name>.json. Out directory will be
                        created if it does not exist and individual files will
                        be overwritten if they exist. Executable bulk-details
                        from node-google-play-cli is used to communicate with
                        Google Play (https://github.com/dweinstein/node-
                        google-play-cli).
    get_repo_data       Download information about repositories from Github.
                        Read CSV file as input and write information to output
                        CSV file. Use -h or --help for more information.
    match_packages      Match package names to Github repositories. Use -h or
                        --help for more information.
    get_gradle_files    Download gradle files from repositories on Github.
                        Read CSV file as input and write all files to outdir.
                        Additional output is a CSV file with columns
                        has_gradle_files, renamed_to, and not_found added to
                        content of input file. Use -h or --help for more
                        information.
    add_gradle_info     Add columns to CSV file: 'has_gradle_files',
                        'renamed_to', 'not_found' In an earlier version
                        find_gradle_files.py did not write any information to
                        a CSV file but only stored gradle files it found in a
                        directory for each repository. This script parses the
                        directories for all repositories and extends an input
                        CSV file with above mentioned columns. Use -h or
                        --help for more information.
    clone               Clone Github repositories listed in CSV file. The CSV
                        file needs to contain a column full_name that lists
                        the identifier of the Github repository in the format
                        <ownwer-login>/<repo-name>. Repositories can be
                        filitered by a minimum number of commits requirement.
                        Use -h or --help for more information.
    draw_commits        Draw a random sample of commits from GitHub For each
                        package name in PACKAGE_LIST search the respective
                        repository for a manifest file with given package
                        name. Total population of commits consists of all
                        commits changing files under same path as the manifest
                        files. Repositories can be filitered by a minimum
                        number of commits requirement. Use -h or --help for
                        more information.
    mirror_empty_repos  Some repositories are empty after the mirroring
                        script. Fix this by mirroring the repos again.
    consolidate_data    Consolidate repository data from several previous
                        steps. Use -h or --help for more information.
    store_repo_data     Collect meta-data of commits, branches, and tags When
                        creating the Docker image with the graph database,
                        access to Gitlab is not available. Temporarily store
                        all data in CSV files. Use -h or --help for more
                        information.
    store_in_neo4j      Store information in Neo4j graph database. Use -h or
                        --help for more information.
    play_category       Scrape Google Play category data from Google Play.

optional arguments:
  -h, --help            show this help message and exit
  --log LOG             Log file. Default: stderr.
  -v, --verbose         Increase log level. May be used several times.
  -q, --quiet           Decrease log level. May be used several times.
```

## Sub-commands

The app selection process was performed by running several subcommands.

###  Verify Package exists on Google Play

Check HTTP status code of Google Play pages for all package names.

```
usage: gh_android_apps.py verify_play_link [-h] [--input INPUT]
                                           [--output OUTPUT] [--log LOG]
                                           [--include-403]

Filter out package names not available in Google Play.

For each package name in input, check if package name is available in
Google Play. If so, print package name to output.

Input and output have each package name on a separate lines.

Use -h or --help for more information.

optional arguments:
  -h, --help       show this help message and exit
  --input INPUT    File to read package names from. Default: stdin.
  --output OUTPUT  Output file. Default: stdout.
  --log LOG        Log file. Default: stderr.
  --include-403    Include package names which Google Play returns status `403
                   Unauthorized` for.
```

### Download Meta Data for Apps from Google Play

Using
[`node-google-play-cli`](https://github.com/dweinstein/node-google-play-cli),
data for all apps in the dataset is downloaded from Google Play.

```
usage: gh_android_apps.py get_play_data [-h] [--input INPUT] [--outdir OUTDIR]
                                        [--bulk_details-bin BULK_DETAILS_BIN]

Download package meta data from Google Play.

For each package name in input, use node-google-play-cli to fetch meta
data from Google Play and store resulting JSON in out directory.

Input expects each package name on a separate line.

Output JSON files are stored in <outdir>/<package_name>.json. Out
directory will be created if it does not exist and individual files
will be overwritten if they exist.

Executable bulk-details from node-google-play-cli is used to communicate
with Google Play (https://github.com/dweinstein/node-google-play-cli).

optional arguments:
  -h, --help            show this help message and exit
  --input INPUT         File to read package names from. Default: stdin.
  --outdir OUTDIR       Out directory. Default: out/.
  --bulk_details-bin BULK_DETAILS_BIN
                        Path to node-google-play-cli bulk-details binary.
                        Default: /usr/bin/gp-bulk-details
```

### Download Metadata for Repositories from Github

Metadata from GitHub API on all repositories is stored.

```
usage: gh_android_apps.py get_repo_data [-h] [-o OUT] [-p PACKAGE_LIST]

Download information about repositories from Github.

Read CSV file as input and write information to output CSV file.

Use -h or --help for more information.

optional arguments:
  -h, --help            show this help message and exit
  -o OUT, --out OUT     CSV file to write meta data to.
  -p PACKAGE_LIST, --package_list PACKAGE_LIST
                        CSV file that matches package names to a repository.
                        The file needs to contain a column for the package
                        name and a second column with the repo name. Default:
                        stdin.
```

### Deduplicate and Match Apps on Google Play and Github

This is the step where Apps get matched to GitHub repositories.

```
usage: gh_android_apps.py match_packages [-h] [-p PACKAGE_LIST] [-o OUT]
                                         DETAILS_DIRECTORY

Match package names to Github repositories.

Use -h or --help for more information.

positional arguments:
  DETAILS_DIRECTORY     Directory containing JSON files with details from
                        Google Play.

optional arguments:
  -h, --help            show this help message and exit
  -p PACKAGE_LIST, --package_list PACKAGE_LIST
                        CSV file that matches package names to repositories.
                        The file needs to contain a column `package` and a
                        column `all_repos`. `all_repos` contains a comma
                        separated string of Github repositories that include
                        an AndroidManifest.xml file for package name in column
                        `package`. Default: stdin.
  -o OUT, --out OUT     File to write CSV output to. Default: stdout
```

### Download Gradle Files from Repositories

For validation of our dataset we checked how many repositories contain gradle
build configuration.

```
usage: gh_android_apps.py get_gradle_files [-h] [--outdir OUTDIR]
                                           [-r REPO_LIST]
                                           [--output_list OUTPUT_LIST]

Download gradle files from repositories on Github.
Read CSV file as input and write all files to outdir. Additional output is a
CSV file with columns has_gradle_files, renamed_to, and not_found added to
content of input file.

Use -h or --help for more information.

optional arguments:
  -h, --help            show this help message and exit
  --outdir OUTDIR       Directory to safe gradle files to. Default:
                        out/gradle_files.
  -r REPO_LIST, --repo_list REPO_LIST
                        CSV file that contains repository names. The file
                        needs to contain a column 'full_name'. Default: stdin.
  --output_list OUTPUT_LIST
                        CSV file to write updated repository information to.
                        This file will contain the same information as
                        REPO_LIST extended with three columns:
                        has_gradle_files, renamed_to, and not_found. These
                        columns indicate if the repository contains at least
                        one gradle configuration file, the name the repository
                        has been renamed to, and if the repository has not
                        been found anymore, respectively.
```

### Parse Gradle File Availability

Condense information on gradle files from above.

```
usage: gh_android_apps.py add_gradle_info [-h] [--outdir OUTDIR]
                                          [-r REPO_LIST]
                                          [--output_list OUTPUT_LIST]

Add columns to CSV file: 'has_gradle_files', 'renamed_to', 'not_found'

In an earlier version find_gradle_files.py did not write any information to a
CSV file but only stored gradle files it found in a directory for each
repository.

This script parses the directories for all repositories and extends an input
CSV file with above mentioned columns.

Use -h or --help for more information.

optional arguments:
  -h, --help            show this help message and exit
  --outdir OUTDIR       Directory to read gradle files from. Default:
                        out/gradle_files.
  -r REPO_LIST, --repo_list REPO_LIST
                        CSV file that contains repository names. The file
                        needs to contain a column 'full_name'. Default: stdin.
  --output_list OUTPUT_LIST
                        CSV file to write updated repository information to.
                        This file will contain the same information as
                        REPO_LIST extended with three columns:
                        has_gradle_files, renamed_to, and not_found. These
                        columns indicate if the repository contains at least
                        one gradle configuration file, the name the repository
                        has been renamed to, and if the repository has not
                        been found anymore, respectively.
```

### Clone Repositories from Github

Create clones of all repositories in the dataset.
This is not the command we actually used, because we imported all repositories
directly into GitHub.

```
usage: gh_android_apps.py clone [-h] [-o OUTDIR] [-r REPO_LIST]
                                [-c MIN_COMMITS]

Clone Github repositories listed in CSV file.

The CSV file needs to contain a column full_name that lists the identifier of
the Github repository in the format <ownwer-login>/<repo-name>.

Repositories can be filitered by a minimum number of commits requirement.

Use -h or --help for more information.

optional arguments:
  -h, --help            show this help message and exit
  -o OUTDIR, --outdir OUTDIR
                        Prefix to clone repositories into. Default:
                        out/github_repos.
  -r REPO_LIST, --repo_list REPO_LIST
                        CSV file that contains repository names. The file
                        needs to contain a column 'full_name'. Default: stdin.
  -c MIN_COMMITS, --min_commits MIN_COMMITS
                        Minimum number of commits in main branch for
                        repository to be cloned. CSV file needs to have column
                        commit_count for this to work.
```

### Draw sample of commits

This command allows to randomly draw a sample of commits from all repositories
in the dataset directly from GitHub.

This was used for related research, before the local Gitlab clones were
available.

```
usage: gh_android_apps.py draw_commits [-h] [-p PACKAGE_LIST] [-c MIN_COMMITS]
                                       [-s SAMPLE_SIZE] [-o OUTFILE]

Draw a random sample of commits from GitHub

For each package name in PACKAGE_LIST search the respective repository for a
manifest file with given package name. Total population of commits consists of
all commits changing files under same path as the manifest files.

Repositories can be filitered by a minimum number of commits requirement.

Use -h or --help for more information.

optional arguments:
  -h, --help            show this help message and exit
  -p PACKAGE_LIST, --package_list PACKAGE_LIST
                        CSV file that lists package name and repository name
                        in a column each. The file should not have a header.
                        Default: stdin.
  -c MIN_COMMITS, --min_commits MIN_COMMITS
                        Minimum number of commits in main branch for
                        repository to be cloned. CSV file needs to have column
                        commit_count for this to work.
  -s SAMPLE_SIZE, --sample_size SAMPLE_SIZE
                        Number of commits to draw in total. Default: 5000.
  -o OUTFILE, --outfile OUTFILE
                        Path to store output file at. Default: stdout
```

### Fix Gitlab import

The initial import into Gitlab was fragile. This command fixes some of the
issues by mirroring repositories again.

```
usage: gh_android_apps.py mirror_empty_repos [-h] [-o OUTPUT]

Some repositories are empty after the mirroring script.

Fix this by mirroring the repos again.

optional arguments:
  -h, --help            show this help message and exit
  -o OUTPUT, --output OUTPUT
                        File to write output to. Default: stdout.
```

### Combining information gathered in previous steps

This command is used to consolidate data from previous steps to easily import
into Neo4j.

```
usage: gh_android_apps.py consolidate_data [-h] [-o OUTPUT]
                                           ORIGINAL_REPO_LIST NEW_REPO_LIST
                                           MIRRORED_REPO_LIST PACKAGE_LIST
                                           RENAMED_REPOS_LIST

Consolidate repository data from several previous steps.

Use -h or --help for more information.

positional arguments:
  ORIGINAL_REPO_LIST    CSV file as created by subcommand 'get_repo_data' and
                        augmented by subcommand 'add_gradle_info'. This
                        original file is necessary because later versions have
                        non ASCII characters wrongly encoded.
  NEW_REPO_LIST         CSV file generated by external script to import GitHub
                        repositories to a local Gitlab instance. This file has
                        the same content as 'original_file' with some
                        additional columns. Unfortunately, there is an
                        encoding issue.
  MIRRORED_REPO_LIST    CSV file generated by subcommand 'mirror_empty_repos'.
                        This file contains updated information on the snapshot
                        repository in Gitlab.
  PACKAGE_LIST          CSV file that lists package name and repository name
                        in a column each. The file should not have a header.
  RENAMED_REPOS_LIST    CSV file which lists GitHub IDs and new repo names of
                        some renamed repos.

optional arguments:
  -h, --help            show this help message and exit
  -o OUTPUT, --output OUTPUT
                        File to write output CSV to. Default: stdout.
```

### Exporting Git history into CSV files

With this command high level informatoin of Git commits, branches, tags, and
the repositories is stored in CSV file so they can be distributed and imported
into Neo4j.

```
usage: gh_android_apps.py store_repo_data [-h]
                                          [--gitlab-repos-dir GITLAB_REPOS_DIR]
                                          [--gitlab-host GITLAB_HOST]
                                          OUTDIR REPOSITORY_LIST

Collect meta-data of commits, branches, and tags

When creating the Docker image with the graph database, access to Gitlab is
not available. Temporarily store all data in CSV files.

Use -h or --help for more information.

positional arguments:
  OUTDIR                Output directory
  REPOSITORY_LIST       CSV file that lists meta data for repositories and
                        their snapshots on Gitlab.

optional arguments:
  -h, --help            show this help message and exit
  --gitlab-repos-dir GITLAB_REPOS_DIR
                        Local path to repositories of Gitlab user `gitlab`.
                        Default: /var/opt/gitlab/git-data/repositories/gitlab
  --gitlab-host GITLAB_HOST
                        Hostname Gitlab instance is running on. Default:
                        http://145.108.225.21
```

### Importing metadata into Neo4j

```
usage: gh_android_apps.py store_in_neo4j [-h] [--neo4j-host NEO4J_HOST]
                                         [--neo4j-port NEO4J_PORT]
                                         PLAY_STORE_DETAILS_DIR
                                         REPO_DETAILS_DIR REPOSITORY_LIST

Store information in Neo4j graph database.

Use -h or --help for more information.

positional arguments:
  PLAY_STORE_DETAILS_DIR
                        Directory containing JSON files with details from
                        Google Play.
  REPO_DETAILS_DIR      Directory containing CSV files with details from
                        repositories.
  REPOSITORY_LIST       CSV file that lists meta data for repositories and
                        their snapshots on Gitlab.

optional arguments:
  -h, --help            show this help message and exit
  --neo4j-host NEO4J_HOST
                        Hostname Neo4j instance is running on. Default:
                        bolt://localhost
  --neo4j-port NEO4J_PORT
                        Port number of Neo4j instance. Default: 7687
```

### Scraping category information from Google Play

The JSON data collected with `node-google-play-cli` contained empty data for
`appCategory`. We added that information with this script.

```
usage: gh_android_apps.py play_category [-h] PLAY_STORE_DETAILS_DIR

Scrape Google Play category data from Google Play.

positional arguments:
  PLAY_STORE_DETAILS_DIR
                        Directory containing JSON files with details from
                        Google Play.

optional arguments:
  -h, --help            show this help message and exit
```
