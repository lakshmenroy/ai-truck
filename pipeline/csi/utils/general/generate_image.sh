#!/bin/bash

# Description: This script generates PNG and SVG files from DOT files in the 'dotfiles' directory.
# It checks if the Graphviz 'dot' command is installed, and generates images for each DOT file if corresponding 
# PNG and SVG files do not already exist.

# Check if the 'dot' command (from Graphviz) is installed; if not, exit with an error
if ! command -v dot &> /dev/null
then
  echo "dot command could not be found"
  echo "please install graphviz"
  exit
fi

# Define directory paths
DOT_FILES_DIR="/opt/deepstream-app/app/graphs"  # Directory where the DOT files are located
PNG_FILES_DIR="/opt/deepstream-app/app/graphs"  # Directory where PNG files will be saved
SVG_FILES_DIR="/opt/deepstream-app/app/graphs"  # Directory where SVG files will be saved

# Get a list of all DOT files in the DOT_FILES_DIR
DOT_FILES=`ls $DOT_FILES_DIR | grep dot`

# Loop through each DOT file
for dot_file in $DOT_FILES
do
  # # Only generate PNG and SVG files if the corresponding PNG file does not exist
  # if [ ! -f $PNG_FILES_DIR/`echo $dot_file | sed s/.dot/.png/` ]
  # then
    echo -e "\nGenerating $dot_file"
    
    # Generate the output file names for PNG and SVG by replacing '.dot' with '.png' and '.svg'
    png_file=`echo $dot_file | sed s/.dot/.png/`
    svg_file=`echo $dot_file | sed s/.dot/.svg/`

    # Generate the PNG and SVG files from the DOT file using the 'dot' command
    dot -Tpng $DOT_FILES_DIR/$dot_file > $PNG_FILES_DIR/$png_file
    dot -Tsvg $DOT_FILES_DIR/$dot_file > $PNG_FILES_DIR/$svg_file
  # else
  #   # Skip the generation if the corresponding PNG and SVG files already exist
  #   echo -e "\nSkipping $dot_file, png and svg files already exist!"
  #   continue
  # fi
done
