"""
pipeline configuration file
get_packages: returns rez-packages based on a tool
run: runs the specified command
"""

from __future__ import print_function

from rez.resolved_context import ResolvedContext
from rez.package_search import ResourceSearcher
from ilp_bootstrap import Bootstrap
import ilp_bootstrap
import rez
import os
import sys


class ProjectBootstrap(Bootstrap):

    base_package = "base-6"
    base_ui_pyside = "base_ui_pyside-1"
    base_tools_package = "base_tools-1"
    review_machine_name = "omg-05.ilpvfx.hq"

    # ------------------------
    # RENDER PACKAGES
    # ------------------------
    htoa_package = (
        "htoa-6.4.4",
        "htoa_base-6",
        "htoa_utils-1",
        # "lentil-2",
        "ilp_vdb_sample-1",
    )
    htoa_test_package = (
        "htoa-6.4.5",
        "htoa_base-6",
        "htoa_utils-1",
        "ilp_vdb_sample-1",
    )

    mtoa_package = (
        "mtoa-5",
        "mtoa_base-9",
    )
    renderman_package = (
        "renderman-26",
        "renderman_for_houdini-26",
        "renderman_for_houdini_base-0",
    )

    # ------------------------
    # HOUDINI PACKAGES
    # ------------------------

    houdini_package = (
        "houdini-21.0",
        base_package,
        base_ui_pyside,
        "checkmate_houdini-1",
        "houdini_base-7",
        "houdini_utils-6",
        "houdini_sidefxlabs-21",
        "extractor-2",
        "software_utils-2",
        "houdini_shfs-21",
    )

    houdini_tools_package = (
        "osl_shader_collection-0",
        "pgptools-1",
        "groombear-1",
        "job_chain-2",
    )
    ilp_ocean_package = (
        "ilp_ocean_arnold-8",
        "ilp_ocean_houdini-8",
        "ilp_ocean_utils-3",
    )
    hou_fx_plugins = ("axiom-3",)

    # ------------------------
    # MAYA PACKAGES
    # ------------------------

    maya_2024_package = (
        "maya-2024",
        base_package,
        base_ui_pyside,
        "checkmate-2",
        "maya_base-7",
        "maya_utils-3",
        "bifrost-2",
        "bifrost_utils-1",
        "maya_usd-0",
        "maya_usd_base-3",
        "software_utils-2",
    )

    maya_package = (
        "maya-2026.3",
        base_package,
        base_ui_pyside,
        "checkmate-2",
        "maya_base-7",
        "maya_utils-3",
        "bifrost-2",
        "bifrost_utils-1",
        "maya_usd-0",
        "maya_usd_base-3",
        "software_utils-2",
    )
    maya_tools_package = (
        "anim_bot-2",
        "blendshape_manager-0",
        "rigmarole-1",
        "rig_update-2",
        "switcharoo-0",
        "studio_library-2",
        "studio_library_utils-1",
        "maya_redistort-1",
    )

    utils_package = (
        "anim_utils-1",
        "build_utils-0",
        "cfx_utils-0",
        "light_utils-0",
        "rig_utils-1",
        "techanim_utils-0",
        "td_utils-0",
        "usd_utils-0",
    )
    prep_package = ("prep_utils-1",)

    maya_ziva_package = (
        "maya-2023",
        base_package,
        "maya_base-6",
        "ziva_vfx-2",
    )

    packages = dict(
        maya_reference_remap=maya_package + mtoa_package,
        maya_reference_remapper=maya_package + mtoa_package,
        maya=maya_package
        + mtoa_package
        + maya_tools_package
        + utils_package
        + prep_package,
        maya_ziva=maya_ziva_package,
        prman=houdini_package
        + houdini_tools_package
        + renderman_package
        + utils_package,
        prmanfx=houdini_package
        + houdini_tools_package
        + htoa_package
        + utils_package
        + hou_fx_plugins,
        houdini=houdini_package
        + houdini_tools_package
        + htoa_package
        + utils_package
        + ilp_ocean_package,
        houdinifx=houdini_package
        + houdini_tools_package
        + htoa_package
        + utils_package
        + ilp_ocean_package
        + hou_fx_plugins,
        dev_houdini=houdini_package
        + houdini_tools_package
        + htoa_test_package
        + utils_package
        + ilp_ocean_package,
        blender=(
            "blender-4.5",
            "blender_base-1",
        ),
        bundler=(
            "bundler-0",
            "bundler_base-0",
        ),
        checkmate=(
            base_package,
            base_ui_pyside,
            "checkmate-2",
            "PySide2-5",
        ),
        das_element=(
            "das_element_library_selector-0",
            "das_element-2",
        ),
        dailies=(
            base_package,
            base_tools_package,
            "PySide2-5",
        ),
        deliver_playlist=(
            "gaffer-1.3",
            "gaffer_plugins-2",
            "gaffer_deliveries-2",
        ),
        depview=("ilp_sg_dependency_viewer-0",),
        gaffer=(
            "gaffer-1",
            base_package,
            base_ui_pyside,
            "gaffer_base-1",
            "gaffer_utils-1",
            "gaffer_deliveries-3",
        ),
        generate_editorial_quicktime=("editorial_utils-1",),
        hiero=(
            "nuke-16.0",
            base_package,
            base_ui_pyside,
            "hiero_base-0",
            "hiero_utils-0",
        ),
        ingest=("ingest_apps_ingest-1", "ingest_utils-2"),
        ingest_prep=(
            base_package,
            "prep_utils-1",
        ),
        krita=(
            "krita-4",
            "krita_base-0",
        ),
        nuke=(
            "nuke-13.2",
            base_package,
            base_ui_pyside,
            "checkmate-2",
            "nuke_base-6",
            "ldpk-2",
            "neatvideo-5",
            "nuke_deep-4",
            "nuke_plugins-3",
            "nuke_utils-4",
            "light_utils-0",
            "optical_flare-1",
            "nnsuperresolution-4",
            "nnflowvector-2",
            "nncleanup-1",
            "nuke_stamps-2",
            "point_render-1.3",
            "extractor-2",
            "keentools-2023",
            "nuke_queue-0",
            "cattery-1",
            "pixelfudger-3",
            "mldepth-1",
            "mlretime-1",
            "mlhumanmatte-1",
            "mlplatematte-2",
            "mltrimapmatte-1",
            "mldeblur-1",
            "mlvignette-1",
        )
        + prep_package,
        nuke16=(
            "nuke-16.0",
            base_package,
            base_ui_pyside,
            "checkmate-2",
            "nuke_base-6",
            "nuke_utils-4",
            "nuke_plugins-4",
            "nuke_deep-5",
            "neatvideo-6",
            "point_render-1.3",
            "extractor-2",
            "pixelfudger-3",
            "nuke_queue-0",
            "nuke_stamps-2",
            "ldpk-2",
            "cattery-1",
            "nnsuperresolution-4",
            "nnflowvector-2",
            "nncleanup-1",
            "gs_ofx-1",
            "mldepth-1",
            "mlretime-1",
            "mlhumanmatte-1",
            "mlplatematte-2",
            "mltrimapmatte-1",
            "mldeblur-1",
            "mlvignette-1",
        )
        + prep_package,
        mari=(
            "mari-7",
            base_package,
            base_ui_pyside,
            "mari_base-4",
            "mari_utils-3",
            "mari_extension_pack-6",
        ),
        motionbuilder=(
            "motion_builder-2024",
            "motion_builder_base-3",
            base_package,
            base_ui_pyside,
        ),
        prep=(
            base_package,
            "python-3",
        ),
        production_update=("production_update-2",),
        rv=(
            "rv-2023",
            base_package,
            base_ui_pyside,
            "rv_base-6",
            "rv_utils-6",
            "ilp_sgtk-0.19",
        ),
        rv_rocky8=(
            "rv-2021",
            base_package,
            base_ui_pyside,
            "checkmate-2",
            "rv_base-5",
            "rv_utils-5",
            "ilp_sgtk-0.19",
        ),
        submit_job_chain=(
            base_package,
            "job_chain-2",
            "td_utils-0",
            "PySide2-5",
        ),
        substance_painter=(
            "substance_painter-10",
            base_package,
            base_ui_pyside,
            "substance_painter_base-4",
        ),
        substance_designer=(
            base_package,
            base_ui_pyside,
            "checkmate-2",
            "substance_designer-12",
            "substance_designer_base-1",
        ),
        unreal=("unreal_engine-5",),
        deliver=("deliver-0",),
    )

    packages["das-element"] = packages["das_element"]
    packages["das-element-ingest"] = packages["das_element"]
    packages["mari-local"] = packages["mari"]
    packages["houdinicore"] = packages["houdini"]
    packages["houdinifx"] = packages["houdini"]
    packages["obj2abc"] = packages["maya"]

    def _get_show_packages(self):
        project_path = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        user_pkg_path = os.path.expanduser("~/packages")
        show_pkg_path = os.path.join(project_path, ".ilp", "packages")
        show_pkg_name = "show_{}".format(os.path.basename(project_path))

        searcher = ResourceSearcher(
            package_paths=[user_pkg_path, show_pkg_path],
            resource_type="package",
            validate=True,
        )
        results = searcher.search()
        for r in results[1]:
            if (r.resource.name == show_pkg_name) and (r.validation_error is None):
                return (r.resource.name,)

        return tuple()

    def run_command(self, argv, packages, **kwargs):
        kwargs.setdefault("block", True)
        show_pkgs = self._get_show_packages()
        packages = packages + show_pkgs
        context = ResolvedContext(package_requests=packages)
        return context.execute_shell(command=argv, **kwargs)

    def run(self, *argv, **kwargs):
        packages = self.packages.get(argv[0])
        return self.run_command(argv, packages, **kwargs)


ilp_bootstrap.Bootstrap = ProjectBootstrap
