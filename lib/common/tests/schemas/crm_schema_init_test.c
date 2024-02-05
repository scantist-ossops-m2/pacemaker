/*
 * Copyright 2023-2024 the Pacemaker project contributors
 *
 * The version control history for this file may have further details.
 *
 * This source code is licensed under the GNU General Public License version 2
 * or later (GPLv2+) WITHOUT ANY WARRANTY.
 */

#include <crm_internal.h>

#include <ftw.h>
#include <unistd.h>

#include <crm/common/xml.h>
#include <crm/common/unittest_internal.h>
#include <crm/common/xml_internal.h>

/* crm_schema_init is best tested by writing tests for all the other public
 * functions it calls.  However, it's useful to have a test to make sure
 * incorporating a second directory of schema files (like may be seen on
 * Pacemaker Remote nodes) works.
 */

static char *remote_schema_dir = NULL;

static int
symlink_schema(const char *tmpdir, const char *target_file, const char *link_file) {
    int rc = 0;
    char *oldpath = NULL;
    char *newpath = NULL;

    oldpath = crm_strdup_printf("%s/%s", PCMK__TEST_SCHEMA_DIR, target_file);
    newpath = crm_strdup_printf("%s/%s", tmpdir, link_file);

    rc = symlink(oldpath, newpath);

    free(oldpath);
    free(newpath);
    return rc;
}

static int
rm_files(const char *pathname, const struct stat *sbuf, int type, struct FTW *ftwb)
{
    return remove(pathname);
}

static int
rmtree(const char *dir) {
    return nftw(dir, rm_files, 10, FTW_DEPTH|FTW_MOUNT|FTW_PHYS);
}

static int
setup(void **state) {
    char *dir = NULL;

    /* Create a directory to hold additional schema files.  These don't need
     * to be anything special - we can just copy existing schemas but give
     * them new names.
     */
    dir = crm_strdup_printf("%s/test-schemas.XXXXXX", pcmk__get_tmpdir());
    remote_schema_dir = mkdtemp(dir);

    if (remote_schema_dir == NULL) {
        free(dir);
        return -1;
    }

    /* Add new files to simulate a remote node not being up-to-date.  We can't
     * add a new major version here without also creating an XSL transform, and
     * we can't add an older version (like 1.1 or 2.11 or something) because
     * remotes will only ever ask for stuff newer than their newest.
     */
    if (symlink_schema(dir, "pacemaker-3.0.rng", "pacemaker-3.1.rng") != 0) {
        rmdir(dir);
        free(dir);
        return -1;
    }

    if (symlink_schema(dir, "pacemaker-3.0.rng", "pacemaker-3.2.rng") != 0) {
        rmdir(dir);
        free(dir);
        return -1;
    }

    setenv("PCMK_remote_schema_directory", remote_schema_dir, 1);
    setenv("PCMK_schema_directory", PCMK__TEST_SCHEMA_DIR, 1);

    /* Do not call crm_schema_init here because that is the function we're
     * testing.  It needs to be called in each unit test.  However, we can
     * call crm_schema_cleanup in teardown().
     */

    return 0;
}

static int
teardown(void **state) {
    int rc = 0;
    char *f = NULL;

    crm_schema_cleanup();
    unsetenv("PCMK_remote_schema_directory");
    unsetenv("PCMK_schema_directory");

    rc = rmtree(remote_schema_dir);

    free(remote_schema_dir);
    free(f);
    return rc;
}

static void
extra_schema_files(void **state) {
    crm_schema_init();

    pcmk__log_known_schemas();

    /* Just iterate through the list of schemas and make sure everything
     * (including the new schemas we loaded from a second directory) is in
     * the right order.
     */
    assert_string_equal("pacemaker-1.0", get_schema_name(0));
    assert_string_equal("pacemaker-1.2", get_schema_name(1));
    assert_string_equal("pacemaker-2.0", get_schema_name(3));
    assert_string_equal("pacemaker-3.0", get_schema_name(14));
    assert_string_equal("pacemaker-3.1", get_schema_name(15));
    assert_string_equal("pacemaker-3.2", get_schema_name(16));

    /* This will one day be removed */
    assert_string_equal("pacemaker-next", get_schema_name(17));

    assert_string_equal("none", get_schema_name(18));
}

PCMK__UNIT_TEST(setup, teardown,
                cmocka_unit_test(extra_schema_files));
