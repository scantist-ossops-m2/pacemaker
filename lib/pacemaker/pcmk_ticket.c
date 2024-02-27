/*
 * Copyright 2024 the Pacemaker project contributors
 *
 * The version control history for this file may have further details.
 *
 * This source code is licensed under the GNU General Public License version 2
 * or later (GPLv2+) WITHOUT ANY WARRANTY.
 */

#include <crm_internal.h>

#include <crm/cib/internal.h>

#include <pacemaker.h>
#include <pacemaker-internal.h>

#include "libpacemaker_private.h"

int
pcmk__ticket_constraints(pcmk__output_t *out, cib_t *cib, const char *ticket_id)
{
    int rc = pcmk_rc_ok;
    xmlNode *result = NULL;
    const char *xpath_base = NULL;
    char *xpath = NULL;

    CRM_ASSERT(out != NULL && cib != NULL);

    xpath_base = pcmk_cib_xpath_for(PCMK_XE_CONSTRAINTS);
    CRM_ASSERT(xpath_base != NULL);

    if (ticket_id != NULL) {
        xpath = crm_strdup_printf("%s/" PCMK_XE_RSC_TICKET "[@" PCMK_XA_TICKET "=\"%s\"]",
                                  xpath_base, ticket_id);
    } else {
        xpath = crm_strdup_printf("%s/" PCMK_XE_RSC_TICKET, xpath_base);
    }

    rc = cib->cmds->query(cib, (const char *) xpath, &result,
                          cib_sync_call | cib_scope_local | cib_xpath);
    rc = pcmk_legacy2rc(rc);

    if (result != NULL) {
        out->message(out, "ticket-constraints", result);
        free_xml(result);
    }

    free(xpath);
    return rc;
}

int
pcmk_ticket_constraints(xmlNodePtr *xml, const char *ticket_id)
{
    pcmk__output_t *out = NULL;
    int rc = pcmk_rc_ok;
    cib_t *cib = NULL;

    rc = pcmk__setup_output_cib_sched(&out, &cib, NULL, xml);
    if (rc != pcmk_rc_ok) {
        goto done;
    }

    rc = pcmk__ticket_constraints(out, cib, ticket_id);

done:
    if (cib != NULL) {
        cib__clean_up_connection(&cib);
    }

    pcmk__xml_output_finish(out, pcmk_rc2exitc(rc), xml);
    return rc;
}
