# Slonik 27B patches for a PostgreSQL pruning bug

We introduced a small defect into PostgreSQL 18.6 for this experiment. A LIST partition could disappear from a query plan when one arm of an OR matched only the DEFAULT partition. The model received the SQL reproducer and a source snapshot without upstream history.

The patches apply independently to the same defective snapshot. The table reports the final patches, including the two follow-ups.

| Build | Patch | First attempt | Independent rows and plans | Core regressions |
|---|---|---|---:|---:|
| oQ8 | [Diff](patches/oq8.patch) | C fix, test added in a follow-up with auto-approval | 15/15 | 231/231 |
| oQ6e | [Diff](patches/oq6e.patch) | C fix and regression test | 15/15 | 231/231 |
| oQ4e | [Diff](patches/oq4e.patch) | Output limit reached before a diff, patch and test on the second attempt | 15/15 | 231/231 |

We also applied the SQL and expected-output changes from each final patch to the defective C build. Each new test failed on its own expected output, then passed with the corresponding C fix.

## Reproduce a run

Run this from the root of a fresh clone of this repository, using the usual PostgreSQL build dependencies. Choose one model patch per source and build directory.

```sh
bench="$PWD"
git clone https://github.com/postgres/postgres.git
git -C postgres checkout --detach 63d9e26c27b9965a78f0d59512a80d84935a7c4b
git -C postgres apply "$bench/patches/fixture.patch"
git -C postgres apply "$bench/patches/oq6e.patch"

mkdir build
cd build
CFLAGS=-O0 ../postgres/configure --enable-cassert
make -j6
make -j6 install DESTDIR="$PWD/install"
python3 "$bench/verify.py" "$PWD/install/usr/local/pgsql/bin"
make -j6 check
```

The verifier starts its own temporary server on a Unix socket and prints row and plan checks as JSON. With just the fixture patch applied, eight checks should fail. On the clean revision and on each final candidate, all 15 should pass.

The baseline is upstream PostgreSQL at revision `63d9e26c27b9965a78f0d59512a80d84935a7c4b`. The injected defect and the model changes are separate diffs. The [PostgreSQL copyright and license notice](LICENSE) accompanies the upstream code in the patches.

[Slonik model and training paper](https://huggingface.co/dglhf/Slonik)
