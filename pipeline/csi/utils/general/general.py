import sys
import logging
import argparse

import gi  # GStreamer
gi.require_version("Gst", "1.0")
from gi.repository import Gst


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments.

    :return: Parsed arguments as a Namespace object.
    """
    parser = argparse.ArgumentParser(description="DeepStream Application Help ")

    parser.add_argument(
        "-i",
        "--input",
        nargs="+",
        required=True,
        help="Path to input H265 elementry stream"
    )

    parser.add_argument(
        "-l",
        "--logging",
        action="store_true",
        default=False,
        dest="logging",
        help="Enable console/file logging",
    )

    parser.add_argument(
        "-mp",
        "--measure-performance",
        action="store_true",
        default=False,
        dest="measure_performance",
        help="Enable perf callback",
    )

    parser.add_argument(
        "-ml",
        "--measure-latency",
        action="store_true",
        default=False,
        dest="measure_latency",
        help="Enable latency measurement",
    )

    parser.add_argument(
        "-csi",
        "--enable-csi",
        action="store_true",
        default=False,
        dest="enable_csi",
        help="Enable csi computation",
    )

    parser.add_argument(
        "-scsi",
        "--save-csi-as-csv",
        action="store_true",
        default=False,
        dest="csi_as_csv",
        help="Enable saving csi as csv file",
    )

    parser.add_argument(
        "-smp",
        "--save-masks-and-probs",
        action="store_true",
        default=False,
        dest="save_masks_and_probs",
        help="Enable saving masks and probabilities",
    )

    # # Check input arguments
    # if len(sys.argv) == 1:
    #     parser.print_help(sys.stderr)
    #     logging.error(msg="ArgumentParser error")
    #     sys.exit(1)

    args = parser.parse_args()

    # Validate the input URIs: 
    # ensure front at pad_index=0 and rear at pad_index=1
    uris = args.input

    if len(uris) != 2:
        msg = (
            f"Invalid input detected: "
            f"Expected 'front-stream' at position '0', "
            f"Expected 'rear-stream' at position '1'"
        )
        logging.error(msg=msg)
        sys.stderr.write(msg + "\n")
        sys.exit(-1)
   
    front_uri = uris[0]
    rear_uri = uris[1]
    if "file://" in front_uri or "file://" in rear_uri:
        if "front" not in front_uri or "rear" not in rear_uri:
            msg = (
                f"Invalid input order detected: "
                f"Expected 'front' at position 0, got: {front_uri}, "
                f"Expected 'rear' at position 1, got: {rear_uri}"
            )
            logging.error(msg=msg)
            sys.stderr.write(msg + "\n")
            sys.exit(-1)

    return args


def cb_newpad(decodebin,
              decoder_src_pad, data):
    logging.info(msg="In cb_newpad\n")
    caps = decoder_src_pad.get_current_caps()
    if not caps:
        caps = decoder_src_pad.query_caps()
    gststruct = caps.get_structure(0)
    gstname = gststruct.get_name()
    source_bin = data
    features = caps.get_features(0)

    # Need to check if the pad created by the decodebin is for video and not
    # audio.
    logging.info(msg=f"gstname={gstname}")
    if (gstname.find("video") != -1):
        # Link the decodebin pad only if decodebin has picked nvidia
        # decoder plugin nvdec_*. We do this by checking if the pad caps contain
        # NVMM memory features.
        logging.info(msg=f"features={features}")
        if features.contains("memory:NVMM"):
            # Get the source bin ghost pad
            bin_ghost_pad = source_bin.get_static_pad("src")
            if not bin_ghost_pad.set_target(decoder_src_pad):
                sys.stderr.write(" Failed to link decoder src pad to source bin ghost pad\n")
                logging.error(msg="Failed to link decoder src pad to source bin ghost pad\n")
        else:
            logging.error(msg="Error: Decodebin did not pick nvidia decoder plugin.\n")
            sys.stderr.write(" Error: Decodebin did not pick nvidia decoder plugin.\n")


def decodebin_child_added(child_proxy,
                          Object,
                          name,
                          user_data):
    logging.info(msg=f"Decodebin child added: {name}\n")
    if (name.find("decodebin") != -1):
        Object.connect("child-added", decodebin_child_added, user_data)

    if "source" in name:
        source_element = child_proxy.get_by_name("source")
        if source_element.find_property("drop-on-latency") != None:
            Object.set_property("drop-on-latency", True)


def create_source_bin(index,
                      uri):
    # Create a source GstBin to abstract this bin's content from the rest of the
    # pipeline
    bin_name = "source-bin-%02d" % index
    logging.info(msg=f"Creating source bin{bin_name}\n")
    nbin = Gst.Bin.new(bin_name)
    if not nbin:
        logging.error(msg="Unable to create source bin\n")
        sys.stderr.write(" Unable to create source bin\n")

    # Source element for reading from the uri.
    # We will use decodebin and let it figure out the container format of the
    # stream and the codec and plug the appropriate demux and decode plugins
    uri_decode_bin = Gst.ElementFactory.make("uridecodebin", "uri-decode-bin")
    if not uri_decode_bin:
        logging.error(msg="Unable to create uri decode bin\n")
        sys.stderr.write(" Unable to create uri decode bin\n")
    # We set the input uri to the source element
    uri_decode_bin.set_property("uri", uri)
    # Connect to the "pad-added" signal of the decodebin which generates a
    # callback once a new pad for raw data has beed created by the decodebin
    uri_decode_bin.connect("pad-added", cb_newpad, nbin)
    uri_decode_bin.connect("child-added", decodebin_child_added, nbin)

    # We need to create a ghost pad for the source bin which will act as a proxy
    # for the video decoder src pad. The ghost pad will not have a target right
    # now. Once the decode bin creates the video decoder and generates the
    # cb_newpad callback, we will set the ghost pad target to the video decoder
    # src pad.
    Gst.Bin.add(nbin, uri_decode_bin)
    bin_pad = nbin.add_pad(Gst.GhostPad.new_no_target("src", Gst.PadDirection.SRC))
    if not bin_pad:
        logging.error(msg="Failed to add ghost pad in source bin\n")
        sys.stderr.write(" Failed to add ghost pad in source bin\n")
        return None

    return nbin


def sec_to_hhmmss(seconds: float) -> str:
    """
    Convert seconds to HH:MM:SS format.

    :param seconds: Number of seconds to convert.

    :return: The formatted seconds.
    """
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)

    return f"{h:02}:{m:02}:{s:02}"
