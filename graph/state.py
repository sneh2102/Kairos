from typing import Annotated, TypedDict
import operator


def merge_dicts(left: dict, right: dict) -> dict:
    """Reducer for `sections`: lets the 3 parallel writer nodes each update
    their own key without clobbering the others. `next_job` resets the whole
    dict between jobs by returning all keys, which fully overwrites via `right`."""
    return {**left, **right}


class ScrapeState(TypedDict):
    jobs: list[dict]                       # raw scraped candidates
    screened: Annotated[list[dict], operator.add]


class ApplyState(TypedDict):
    jobs: list[dict]                       # approved jobs (from JobsDB)
    job_index: int
    current_job: dict

    cover_letter: str
    sections: Annotated[dict[str, str], merge_dicts]  # header, education, skills, experience, projects

    ats_score: int
    ats_feedback: dict
    ats_iteration: int
    ats_passed: bool
    best_score: int
    no_improve: int
    _sections_to_rewrite: list[str]        # scratch: set by check_ats, read by its own router
    _best_sections: dict                   # snapshot of the highest-scoring version so far —
                                           # save_output keeps this if a rebuild made things worse

    results: Annotated[list[dict], operator.add]
