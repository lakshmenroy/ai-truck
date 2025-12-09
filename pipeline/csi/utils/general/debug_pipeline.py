import os
import subprocess


def create_pipeline_topology_graph(dot_filename: str) -> None:
    """
    Creates a graphical representation of a GStreamer pipeline from a DOT file and generates an image.

    :param dot_filename: The name of the DOT file (without the '.dot' extension) 
                         that represents the pipeline topology.
                          
    :return: None.
    """
    # Check if the DOT file representing the pipeline's topology already exists
    if os.path.exists(f"{os.environ['GST_DEBUG_DUMP_DOT_DIR']}/{dot_filename}.dot"):
        os.chdir(os.environ['GST_DEBUG_DUMP_DOT_DIR'])  # Change to the directory containing the DOT file
        os.system("chmod +x /opt/deepstream-app/app/utils/general/generate_image.sh")  # Grant executable permissions to the shell script
        subprocess.run(["/opt/deepstream-app/app/utils/general/generate_image.sh"])  # Execute the shell script to generate the image
        # os.chdir("..")  # Return to the original directory
