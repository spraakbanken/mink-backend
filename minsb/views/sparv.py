"""Routes related to Sparv."""

import os
import re

import owncloud
from flask import Blueprint, current_app, request

from minsb import utils

bp = Blueprint("sparv", __name__)


@bp.route("/run-sparv", methods=["PUT"])
@utils.login()
def run_sparv(oc, corpora, corpus_id):
    """Run Sparv on given corpus."""
    # TODO: What input args do we need besides corpus_id? Maybe the export format (optionally)?
    return utils.error_response("Not yet implemented!"), 501


@bp.route("/sparv-status", methods=["GET"])
@utils.login()
def sparv_status(oc, corpora, corpus_id):
    """Check the annotation status for a given corpus."""
    # TODO: Check if this is even possible in Sparv.
    return utils.error_response("Not yet implemented!"), 501
