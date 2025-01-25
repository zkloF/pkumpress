from PyQt5 import QtWidgets, QtCore, QtGui
from subprocess import run, CalledProcessError
from PyQt5.QtCore import (QMimeData, QProcess, QRect, Qt, QSize, QPoint, pyqtSignal, QThread)
from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout,
        QWidget, QLabel, QApplication, QPushButton,
        QSizePolicy, QMainWindow, QTabWidget, QGroupBox,
        QFrame, QDialog, QComboBox, QFileDialog,
        QLineEdit, QProgressBar, QMessageBox, QCheckBox,
        QScrollArea, QStackedWidget, QTextEdit,
        QSpacerItem, QGraphicsView, QGraphicsScene,
        QGraphicsPixmapItem, QGraphicsTextItem, QLayout)
from PyQt5.QtGui import (QFont, QMovie, QPixmap,
        QPainter, QImage, QIcon, QMouseEvent,
        QColor, QPalette, QFontDatabase)
from auth_window import AuthWindow
from logs.preview_window import WatermarkPreview, PreviewWindow
import sys
import os
import subprocess
import cv2
import re
import datetime




############################################################
###VIDEO_COMPRESSOR!!!#####
###VIDEO_COMPRESSOR!!!#####
###VIDEO_COMPRESSOR!!!#####
###VIDEO_COMPRESSOR!!!#####
###VIDEO_COMPRESSOR!!!#####


# Constants
DEFAULT_CRF_VALUES = {
    "Low": [18, 19, 20, 21, 22],
    "Medium": [23, 24, 25, 26],
    "High": [27, 28, 29, 30, 31]
}


def has_audio_stream(video_path):
    try:
        cmd = ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "compact=p=0:nk=1", video_path]
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True  # Audio stream found
    except subprocess.CalledProcessError:
        return False  # No audio stream found


class VideoCompressor(QtCore.QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(int, str)
    output_line = pyqtSignal(str) #TERMINAL

    def __init__(self, file_path, output_path="", crf_value=23,
                video_codec="libx264", watermark_path="", x=0, y=0, preset="medium"):
        super().__init__()
        self.file_path = file_path
        self.output_path = output_path
        self.crf_value = crf_value
        self.video_codec = video_codec
        self.watermark_path = watermark_path
        self.preset = preset
        self.x = x
        self.y = y

    def run(self):
        try:
            ffprobe_command = [
                "ffprobe",
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=nb_frames",
                "-of", "default=nokey=1:noprint_wrappers=1",
                self.file_path
            ]
            ffprobe_process = subprocess.run(ffprobe_command, capture_output=True, text=True, check=True)
            total_frames = int(ffprobe_process.stdout.strip())

            ffmpeg_command = ["ffmpeg", "-i", self.file_path]



            if self.watermark_path and os.path.exists(self.watermark_path):
                ffmpeg_command.extend([
                    "-i", self.watermark_path,
                    "-filter_complex", f"[1:v]scale=45:45[wm];[0:v][wm]overlay={self.x}:{self.y}[out]",
                    "-map", "[out]"
                ])

            ffmpeg_command.extend([
                "-c:v", self.video_codec, "-preset", self.preset,
                "-crf", str(self.crf_value)
            ])
            if has_audio_stream(self.file_path): #Check if has audio stream
                ffmpeg_command.extend(["-c:a", "aac", "-b:a", "128k"]) #If has audio stream add the options
            else:
                ffmpeg_command.extend(["-an"]) #If not has audio stream add the option to remove audio stream

            ffmpeg_command.append(self.output_path)
            process = subprocess.Popen(ffmpeg_command, stderr=subprocess.PIPE, text=True)
            for line in iter(process.stderr.readline, ''):
                self.output_line.emit(line.strip())
                frame_match = re.search(r"frame=\s*(\d+)", line)
                if frame_match and total_frames > 0:
                    processed_frames = int(frame_match.group(1))
                    progress = int((processed_frames / total_frames) * 100)
                    self.progress.emit(progress)

            process.wait()
            return_code = process.returncode
            self.finished.emit(return_code, "") # Emit empty string for error message if successful
            if return_code != 0:
                self.output_line.emit(f"FFmpeg exited with code: {return_code}")
                full_error = process.stderr.read()
                self.output_line.emit(f"Full error output:\n{full_error}")

        except (subprocess.CalledProcessError, FileNotFoundError, ValueError, OSError) as e: #Add OSError
            error_message = str(e)
            self.output_line.emit(f"Error: {error_message}") # Emit the error
            self.finished.emit(-1, error_message)
        except Exception as e:
            error_message = "An unexpected error occurred in the compression thread: " + str(e)
            import traceback
            traceback.print_exc() #Print the full traceback to the console
            self.output_line.emit(f"Error: {error_message}")
            self.finished.emit(-1, error_message)



######################################################
###DRAG_&_DROP!!!#####
###DRAG_&_DROP!!!#####
###DRAG_&_DROP!!!#####
###DRAG_&_DROP!!!#####



class DragDropFrame(QFrame):
    filesDropped = pyqtSignal(list)
    compressionFinished = pyqtSignal(int, str)
    compressionStarted = pyqtSignal() # New signal
    compressionEnded = pyqtSignal() # New signal
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setAcceptDrops(True)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setAlignment(Qt.AlignCenter)


        self.setup_ui() # Combined UI setup

        self.compressing = False
        self.dropped_files = []
        self.compress_queue = []

        
        self.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Expanding)
    def setup_ui(self):
        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Sunken)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Expanding)
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor("#E0FFFF"))
        self.setPalette(palette)
        self.setAutoFillBackground(True)
        self.setMinimumSize(300, 200)
        self.setMaximumSize(500, 400)

        self.label = QLabel()
        self.main_layout.addWidget(self.label)

        self.progress_label = QLabel()
        self.progress_label.setAlignment(Qt.AlignCenter)
        self.progress_label.hide()
        self.main_layout.addWidget(self.progress_label)


        

        # Container Widget for GIF and Text (Important!)
        self.initial_widget = QWidget(self) # No parent
        self.content_layout = QVBoxLayout(self.initial_widget)
        self.content_layout.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.initial_widget) #Add the content widget to the main layout

        self.load_image()



###########################################################
#################DRAG_DROP_VISUAL##########################
#####DRAG_DROP_VISUAL#####

    def update_progress_display(self, progress, y_offset=-21):
        if hasattr(self, 'compressing_label'):
            self.main_layout.removeWidget(self.compressing_label)
            self.compressing_label.deleteLater()
            del self.compressing_label
        self.compressing_icons(progress, y_offset) #Call compressing_icons with progress


        self.progress_label.show() #Hide the main label
        self.progress_label.raise_() #Bring to front
        

        QApplication.processEvents()

    def reset_display(self):

        
        self.progress_label.hide()
        self.initial_widget.show()
        self.compressing_label.hide()
        self.loaded_label.hide()
        self.dropped_files.clear()
        
        self.main_window.progress_bar.hide()
        self.main_window.progress_bar.setValue(0)
        self.main_window.progress_bar.setFormat("")
        self.main_window.process_output.show()


  
    def create_combined_pixmap(self, image_path, text):
        try:
            pixmap = QPixmap(image_path)
            if pixmap.isNull():
                raise FileNotFoundError(f"Image not found: {image_path}")

            scaled_pixmap = pixmap.scaled(60, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation) # Fixed size scaling
            text_pixmap = QPixmap(250, 50)
            text_pixmap.fill(Qt.transparent)
            painter = QPainter(text_pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            font = QFont("Arial", 12)
            painter.setFont(font)
            painter.setPen(Qt.black)
            text_rect = painter.boundingRect(0, 0, 250, 50, Qt.AlignHCenter | Qt.AlignVCenter, text)
            painter.drawText(text_rect, Qt.AlignHCenter | Qt.AlignVCenter, text)
            painter.end()

            combined_size = QSize(max(scaled_pixmap.width(), text_pixmap.width()), scaled_pixmap.height() + text_pixmap.height() + 10)
            combined_pixmap = QPixmap(combined_size)
            combined_pixmap.fill(Qt.transparent)

            painter = QPainter(combined_pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            drop_x = (combined_pixmap.width() - scaled_pixmap.width()) // 2
            painter.drawPixmap(drop_x, 0, scaled_pixmap)
            text_x = (combined_pixmap.width() - text_pixmap.width()) // 2
            painter.drawPixmap(text_x, scaled_pixmap.height() + 10, text_pixmap)
            painter.end()
            return combined_pixmap
        except FileNotFoundError as e:
            print(f"Error loading image: {e}")
            return None
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return None
        

    def load_image(self):
        # Clear existing layout items in content_layout
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        movie = QMovie("Images/drop.gif")
        if movie.isValid():
            movie_label = QLabel()
            movie_label.setMovie(movie)
            movie.start()
            movie_label.setScaledContents(True)
            movie_label.setFixedSize(100, 100)

            text_label = QLabel("Drag and Drop files here", self)
            text_label.setAlignment(Qt.AlignCenter)

            font = QFont("Arial", 12)
            text_label.setFont(font)
            text_label.setStyleSheet("color: #333333;")

            movie_hbox = QHBoxLayout()
            movie_hbox.setAlignment(Qt.AlignCenter)
            movie_hbox.addWidget(movie_label)

            self.content_layout.addLayout(movie_hbox)
            self.content_layout.addWidget(text_label)

        else:
            print("Error loading GIF")
            pixmap = QPixmap("Images/drop.png")
            if pixmap:
                label = QLabel() #create local label
                label.setPixmap(pixmap)
                label.setAlignment(Qt.AlignCenter)
                self.content_layout.addWidget(label) #Add the label to the content layout





    def loaded_icons(self):
        self.initial_widget.hide()
        self.progress_label.hide()
        self.progress_label.setAlignment(Qt.AlignCenter)
        

        if hasattr(self, 'loaded_label'):
            self.main_layout.removeWidget(self.loaded_label)
            self.loaded_label.deleteLater()
            del self.loaded_label
        
        pixmap = self.create_combined_pixmap("Images/Icons/videoready.svg", "Video File is Ready")
   
        if pixmap:
            label = QLabel()
            label.setPixmap(pixmap)
            label.setAlignment(Qt.AlignCenter)
            self.main_layout.addWidget(label) #add the label to the main layout.
            self.loaded_label = label

    def compressing_icons(self, progress=None, y_offset=-21):
        self.initial_widget.hide()
        self.progress_label.hide()
        self.progress_label.setAlignment(Qt.AlignCenter)

        pixmap = self.create_combined_pixmap("Images/Icons/videoready.svg", "Compressing...")
        if pixmap:
            if progress is not None:
                painter = QPainter(pixmap)
                painter.setRenderHint(QPainter.Antialiasing)
                font = QFont("Arial", 10)
                painter.setFont(font)
                painter.setPen(Qt.white)

                # Calculate text rectangle with offset
                text_rect = painter.boundingRect(pixmap.rect(), Qt.AlignCenter, str(progress) + "%")
                offset_rect = QRect(text_rect.x(), text_rect.y() + y_offset, text_rect.width(), text_rect.height()) #Apply the offset

                painter.drawText(offset_rect, Qt.AlignCenter, str(progress) + "%")
                painter.end()

            label = QLabel()
            label.setPixmap(pixmap)
            label.setAlignment(Qt.AlignCenter)
            self.main_layout.addWidget(label)
            self.compressing_label = label

######################################################           
######################################################       


    def dragEnterEvent(self, event):
        if self.compressing:  # Check if compressing
            event.ignore()  # Reject drops if compressing
            return
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        if self.compressing: #Check if compressing
            return
        event.accept()
        new_files = [url.toLocalFile() for url in event.mimeData().urls()]
        self.dropped_files.extend(new_files)
        print(f"Files dropped: {self.dropped_files}")


        self.initial_widget.hide()
        self.loaded_icons()

 
    def compress_files(self, crf_value, compression_level, video_codec, watermark_path, x, y, preset):
        if self.compressing or not self.dropped_files: #Check if compressing
            return 

        self.loaded_label.hide()
        self.initial_widget.hide()
        preset = self.main_window.preset_combo.currentText()
        self.compressing = True #Set the flag
        self.compress_queue = list(self.dropped_files)
        self.compressionStarted.emit() #Emit signal

        
        self.process_next_file(crf_value, compression_level, video_codec, watermark_path, x, y, preset)

    def process_next_file(self, crf_value, compression_level, video_codec, watermark_path, x, y, preset):
        preset = self.main_window.preset_combo.currentText()
        if not self.compress_queue:  # Queue is empty, all done
            self.compressing = False
 #Reset display after all compression
            self.main_window.compression_finished(0,"") # Tell main window compression has finished
            
            self.compressionEnded.connect(self.compression_finished_single)
            self.compressionEnded.emit() #Emit Signal
            self.compressionFinished.emit(0, "") #Signal the end of all compression
            self.main_window.processing_label.setText("No file processing")
            self.reset_display()
            return

        self.main_window.process_output.show()
        file_path = self.compress_queue.pop(0) #get the first item in the queue
        filename = os.path.basename(file_path)
        base_filename = os.path.splitext(os.path.basename(file_path))[0]
        output_filename = f"{base_filename}_{compression_level}_compressed.mp4"
        output_path = os.path.join(os.path.dirname(file_path), output_filename)
        self.main_window.processing_label.setText(f"Processing: {filename}") # Update the label

        counter = 1
        while os.path.exists(output_path):
            output_filename = f"{base_filename}_{compression_level}_{counter}_compressed.mp4"
            output_path = os.path.join(os.path.dirname(file_path), output_filename)
            counter += 1

        self.video_compressor = VideoCompressor(file_path, output_path, crf_value, video_codec, watermark_path, x, y, preset)
        self.video_compressor.progress.connect(self.main_window.update_progress)
        try:
            self.video_compressor.output_line.disconnect() #Try to disconnect first
        except TypeError:
            pass
        self.video_compressor.output_line.connect(self.main_window.append_process_output)

        self.video_compressor.progress.connect(self.update_progress_display)

        
        self.video_compressor.finished.connect(
            lambda exit_code, error_message: self.compression_finished_single(exit_code, error_message, crf_value, compression_level, video_codec, watermark_path, x, y, preset)
        )
        self.video_compressor.start()

    def compression_finished_single(self, exit_code, error_message, crf_value, compression_level, video_codec, watermark_path, x, y, preset):
        if exit_code != 0:
            QMessageBox.critical(self.main_window, "Compression Error", f"Video compression failed: {error_message}")
        # Process the next file in the queue

        
        
        if not self.compress_queue:
             #Check if the queue is empty before enabling the button again
            self.reset_display()
            self.dropped_files.clear()
            

            self.compressing = False
            self.main_window.processing_label.setText("No file processing") # Reset the label
            self.compressionEnded.emit() #Emit Signal
            self.compressionFinished.emit(exit_code, error_message) #Signal that all compression is finished
            return
        
        
        if hasattr('compressing_label', "loaded_label"): #Check if the label exists
            self.main_layout.removeWidget(self.compressing_label, self.loaded_label) #Remove the label from the layout
            self.compressing_label.deleteLater()
            self.loaded_label.deleteLater() #Delete the label
            del (self.compressing_label, self.loaded_label)
        
            self.reset_display()

        self.process_next_file(crf_value, compression_level, video_codec, watermark_path, x, y, preset)
    
########################################################


########################################################
###MAINWINDOW!!!#####
###MAINWINDOW!!!#####
###MAINWINDOW!!!#####

class MainWindow(QtWidgets.QMainWindow):
    progress_update = pyqtSignal(int) 

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PKumpressor")
        self.setGeometry(100, 100, 500, 800)
        self.setWindowIcon(QIcon("Images/icon.png"))


        self.central_widget = QtWidgets.QWidget(self)
        self.setCentralWidget(self.central_widget)

        self.main_layout = QtWidgets.QVBoxLayout(self.central_widget)

        self.header_label = QLabel()
        self.header_label.setStyleSheet("background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #87CEEB, stop:1 #ADD8E6);")
        self.header_label.setFixedHeight(40)

        self.title_label = QLabel("PKUMPRESSOR")
        self.title_label.setFont(QFont("Arial", 9, QFont.Bold))
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet("color: black;")

        header_layout = QVBoxLayout(self.header_label)
        header_layout.addWidget(self.title_label)

        # ***CREATE the progress bar here***
        self.progress_bar = QProgressBar()
        self.progress_bar.setAlignment(Qt.AlignCenter)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.hide()
###############################################################


###############################################################
        ###DRAG_AND_DROP_SIGNALS####
        ###DRAG_AND_DROP_SIGNALS####
        ###DRAG_AND_DROP_SIGNALS####

        self.drag_drop_frame = DragDropFrame(self)
        self.main_layout.addWidget(self.drag_drop_frame)
        self.drag_drop_frame.filesDropped.connect(self.handle_files_dropped)
        self.drag_drop_frame.compressionFinished.connect(self.all_compression_finished)
        self.drag_drop_frame.compressionStarted.connect(self.disable_buttons)
        self.drag_drop_frame.compressionEnded.connect(self.enable_buttons)
        # Browse File?DIrectory Buttons 
        # Connect signals to enable/disable buttons
        self.drag_drop_frame.compressionStarted.connect(self.disable_buttons)
        self.drag_drop_frame.compressionEnded.connect(self.enable_buttons)
        # Browse File/Watermark
        # Connect signals to enable/disable buttons


###############################################################
        ###VIDEO_FILE_CURRENT_PROCESSING####
        ###VIDEO_FILE_CURRENT_PROCESSING####
        self.processing_label = QLabel("No file processing", self) # Create the label
        self.processing_label.setAlignment(Qt.AlignCenter) #Center the label


###############################################################
        ###PROCESSING_TERMINAL####
        ###PROCESSING_TERMINAL####
        self.terminal_group = QGroupBox("Process Terminal", self)  # Create a QGroupBox
        self.terminal_layout = QVBoxLayout(self.terminal_group) #Layout for the groupbox
        self.process_output = QTextEdit(self)
        self.process_output.setReadOnly(True)
        self.process_output.setFont(QFont("Courier New", 10))
        self.terminal_layout.addWidget(self.process_output) #Add the text edit to the groupbox
        self.terminal_group.setLayout(self.terminal_layout) #Set the layout to the groupbox
        self.terminal_group.setCheckable(True) #Make it checkable (collapsible)
        self.terminal_group.setChecked(False) #Start collapsed


        ###SAVING_PROCESSING_TERMINAL####
        self.log_status_label = QLabel("", self)
        self.log_status_label.setAlignment(Qt.AlignCenter)  # Keep alignment
        self.log_status_label.setStyleSheet("color: green;") #Set color to green
        self.save_logs_checkbox = QCheckBox("Save Logs", self)
        self.save_logs_checkbox.setChecked(False) # Default unchecked

        ###SAVING_TERMINAL_LOGS_LOCATION####   
        self.logs_directory = "PkLogs" #Set the logs directory
        if not os.path.exists(self.logs_directory): #Create the directory if it doesn't exist
            os.makedirs(self.logs_directory)

####################################################################

        self.main_layout.addWidget(self.header_label)

        self.tabs = QTabWidget()
        self.main_layout.addWidget(self.tabs)

        self.main_tab = QWidget()
        self.tools_tab = QWidget()
        self.settings_tab = QWidget()
        self.about_tab = QWidget()

        self.tabs.addTab(self.main_tab, "Main")
        self.tabs.addTab(self.tools_tab, "Tools")
        self.tabs.addTab(self.settings_tab, "Settings")
        self.tabs.addTab(self.about_tab, "About")


        self.watermark_path_edit = QLineEdit()
        self.preview_window = PreviewWindow(self)
        self.watermark_position = QPoint(10, 10) #Store the position
        
        self.setup_main_tab()
        self.setup_other_tabs(self.tools_tab, "Details Content")
        self.setup_settings_tab()
        self.setup_other_tabs(self.about_tab, "About Content")

        self.central_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMaximumSize(500, 800)

        

    def disable_buttons(self):
        self.compress_button.setEnabled(False)
        self.browse_file_button.setEnabled(False)
        self.browse_directory_button.setEnabled(False)
        self.watermark_browse_button.setEnabled(False)
        self.watermark_clear_button.setEnabled(False)
        self.show_preview_button.setEnabled(False)

    def enable_buttons(self):
        self.compress_button.setEnabled(True)
        self.browse_file_button.setEnabled(True)
        self.browse_directory_button.setEnabled(True)
        self.watermark_browse_button.setEnabled(True)
        self.watermark_clear_button.setEnabled(True)
        self.show_preview_button.setEnabled(True)

    def browse_file(self):
        options = QtWidgets.QFileDialog.Options()
        options |= QtWidgets.QFileDialog.DontUseNativeDialog
        options |= QtWidgets.QFileDialog.DontUseCustomDirectoryIcons #Optional
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Select Video Files", "", "Video Files (*.mp4 *.avi *.mov *.mkv);;All Files (*)", options=options)
        if files:
            self.handle_input(files)

    def browse_directory(self):
        options = QtWidgets.QFileDialog.Options()
        options |= QtWidgets.QFileDialog.DontUseNativeDialog
        directory = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Input Directory", "", options=options)
        if directory:
            self.drag_drop_frame.dropped_files = []
            for filename in os.listdir(directory):
                if filename.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):  # Filter video files
                    filepath = os.path.join(directory, filename)
                    self.drag_drop_frame.dropped_files.append(filepath)
            if self.drag_drop_frame.dropped_files:
                self.handle_input(self.drag_drop_frame.dropped_files)  # Process the list of video files
            else:
                QtWidgets.QMessageBox.warning(self, "No Videos Found", "No video files found in the selected directory.")

    def handle_input(self, files):
        # Convert to sets to remove duplicates efficiently
        existing_files = set(self.drag_drop_frame.dropped_files)
        new_files = set(files)
        unique_files = list(existing_files.union(new_files)) # Get the unique set of files

        self.drag_drop_frame.dropped_files = unique_files # Set the new list of unique files
        self.drag_drop_frame.initial_widget.hide()
        self.drag_drop_frame.loaded_icons()
        print(f"Files added: {self.drag_drop_frame.dropped_files}")
    
####################################################
###SETUP_MAIN!!!#####
###SETUP_MAIN!!!#####
###SETUP_MAIN!!!#####


    def setup_main_tab(self):
        main_tab_layout = QVBoxLayout(self.main_tab)
        main_tab_layout.setContentsMargins(10, 10, 10, 10)
        main_tab_layout.setSpacing(10)

        # *** Single horizontal layout for everything ***
        main_content_layout = QHBoxLayout() #Name changed for clarity
        main_content_layout.addWidget(self.drag_drop_frame) 
        
        
        main_tab_layout.addWidget(self.progress_bar)
        
#######################################################
        compression_layout = QHBoxLayout()
        compression_label = QLabel("Compression Level")
        compression_label.setAlignment(Qt.AlignCenter)
        self.compression_combo = QComboBox()
        self.compression_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.compression_combo.addItems(["Low", "Medium", "High"])
        self.compression_number_combo = QComboBox()
        self.compression_combo.currentIndexChanged.connect(self.update_number_combo)
        self.video_codec_combo = QComboBox()
        self.video_codec_combo.addItems(["Codec-264", "Codec-265"]) #Display name
        self.video_codec_map = {"Codec-264": "libx264", "Codec-265": "libx265"} #Add the items
        

        compression_layout.addWidget(compression_label)
        compression_layout.addWidget(self.compression_combo)
        compression_layout.addWidget(self.compression_number_combo)
        compression_layout.addWidget(self.video_codec_combo)
################################################################

        preset_layout = QHBoxLayout() #Create a layout for the preset
        preset_label = QLabel("Preset:")
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(["ultrafast", "superfast", "fast", "medium", "slow", "slower", "veryslow"]) #Add the preset #Set the default preset
        self.preset_combo.currentText()
        self.preset_combo.setCurrentIndex(3)
        preset_layout.addWidget(preset_label) #Add the label and combobox to the layout
        preset_layout.addWidget(self.preset_combo)

        
################################################################
        # Watermark Section
        watermark_layout = QHBoxLayout()
        watermark_label = QLabel("Watermark Image:")
        self.watermark_browse_button = QPushButton("Browse")
        self.watermark_browse_button.clicked.connect(self.browse_watermark)
        self.watermark_clear_button = QPushButton("Clear")
        self.watermark_clear_button.clicked.connect(self.clear_watermark)
        self.show_preview_button = QPushButton("Edit Watermark Location")
        self.show_preview_button.clicked.connect(self.show_preview)
        
        watermark_layout.addWidget(watermark_label)
        watermark_layout.addWidget(self.watermark_path_edit)
        watermark_layout.addWidget(self.watermark_browse_button)
        watermark_layout.addWidget(self.watermark_clear_button)
        watermark_layout.addWidget(self.show_preview_button)

        # Combine Compression and Watermark
        options_layout = QVBoxLayout()
        options_layout.addLayout(compression_layout)
        options_layout.addLayout(preset_layout)
        options_layout.addLayout(watermark_layout)
   

   
#############################################################




        main_content_layout.addLayout(options_layout) #Add the combo box layout to main content layout
        main_content_layout.addStretch(1) #Add stretch to the right

        main_tab_layout.addLayout(main_content_layout) #Add the main content layout to the tab layout
        
        
#############################################################
        browse_layout = QHBoxLayout()
        self.browse_file_button = QPushButton("Browse File")
        self.browse_directory_button =  QPushButton("Browse Directory")
        self.browse_file_button.clicked.connect(self.browse_file)
        self.browse_directory_button.clicked.connect(self.browse_directory)
        browse_layout.addWidget(self.browse_directory_button)
        browse_layout.addWidget(self.browse_file_button)
        main_tab_layout.addLayout(browse_layout)

        ###PROGRESS_BAR&CURRENT_PROCESSING####
        ###PROGRESS_BAR&CURRENT_PROCESSING####
        main_tab_layout.addWidget(self.processing_label)
        main_tab_layout.addWidget(self.progress_bar)
        self.compress_button = QPushButton("Compress")
        self.compress_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed) #Horizontal Expanding and Vertical Fixed
        self.compress_button.setFixedHeight(60)
        font = QFont("Arial", 14)  # Larger font size
        self.compress_button.setFont(font)
        self.compress_button.setStyleSheet("padding: 10px;") 
        main_tab_layout.addWidget(self.compress_button)
        self.compress_button.clicked.connect(lambda: self.start_compression())



        ###PROCESSING_TERMINAL####
        ###PROCESSING_TERMINAL####
        ###PROGRESS_BAR&CURRENT_PROCESSING####
        main_tab_layout.addWidget(self.save_logs_checkbox)
        main_tab_layout.addWidget(self.terminal_group)
        main_tab_layout.addWidget(self.log_status_label)
        
##################################################################################

        # Signal connections should be made AFTER the button is created

        #self.drag_drop_frame.filesDropped.connect(self.handle_files_dropped)
        self.drag_drop_frame.compressionStarted.connect(lambda: self.save_logs_checkbox.setEnabled(False)) #Disable Checkbox
        #self.drag_drop_frame.compressionStarted.connect(lambda: self.compress_button.setEnabled(False))
        self.drag_drop_frame.compressionEnded.connect(lambda: self.save_logs_checkbox.setEnabled(True)) #Disable Checkbox
        #self.drag_drop_frame.compressionEnded.connect(lambda: self.compress_button.setEnabled(True))

        main_tab_layout.addStretch(1)

        self.update_number_combo(self.compression_combo.currentIndex())




    def handle_files_dropped(self, files):
        # Do something with the files, for example enable the compress button
        self.compress_button.setEnabled(bool(files))


    def update_progress(self, progress):
        self.progress_bar.setValue(progress)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.show()
        QApplication.processEvents()


    def append_process_output(self, line):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Check if it's the start of a new file's log
        if not hasattr(self, 'last_processed_file') or (self.drag_drop_frame.compress_queue and self.last_processed_file != self.drag_drop_frame.compress_queue[0]):
            if hasattr(self, 'last_processed_file'):  # Add separator only if it's NOT the very first file
                self.process_output.append("\n######################_COMPRESSED_VIDEOFILES_LOGS_####################\n")
            if self.drag_drop_frame.compress_queue:
                filename = os.path.basename(self.drag_drop_frame.compress_queue[0])
                preset = self.preset_combo.currentText()
                self.process_output.append(f"[{timestamp}] Starting compression for: {filename}  (Preset: {preset})\n")
                self.last_processed_file = self.drag_drop_frame.compress_queue[0]
        
        self.process_output.append(f"[{timestamp}] {line}")
        self.process_output.verticalScrollBar().setValue(self.process_output.verticalScrollBar().maximum())
        if not self.terminal_group.isChecked():
            self.terminal_group.setChecked(True)
        QApplication.processEvents()



###COMPRESSOR_FINISHED!!!#####
###COMPRESSOR_FINISHED!!!#####
###COMPRESSOR_FINISHED!!!#####
###COMPRESSOR_FINISHED!!!#####
###COMPRESSOR_FINISHED!!!#####


    def all_compression_finished(self, exit_code, error_message): #Handle the signal
        self.drag_drop_frame.reset_display()


        if exit_code == 0:
            QtWidgets.QMessageBox.information(self, "Success", "Video compressed successfully!")
        else:
            QtWidgets.QMessageBox.critical(self, "Compression Error", f"Video compression failed: {error_message}")


        if self.save_logs_checkbox.isChecked():
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            log_filename = os.path.join(self.logs_directory, f"compression_log_{timestamp}.txt")
            try:
                with open(log_filename, "a") as log_file:
                    log_file.write(self.preset_combo.currentText())
                    log_file.write("\n###################_PROCESS_TERMINAL_LOGS_######################\n")
                    log_file.write(self.process_output.toPlainText())
                self.log_status_label.setStyleSheet("color: green;") #Set to green for success
                self.log_status_label.setText(f"Logs saved to {log_filename}")
            except Exception as e:
                self.log_status_label.setStyleSheet("color: red;") #Set to red for error
                self.log_status_label.setText(f"Error saving logs: {e}")
                pass
        QtCore.QTimer.singleShot(5000, self.clear_log_status)
        self.preview_window.close()

    def clear_log_status(self): #New method to clear the label
        self.log_status_label.clear()
        self.process_output.clear()
        self.process_output.hide()
        
    def update_number_combo(self, index):
        self.compression_number_combo.clear()
        self.compression_number_combo.addItems([str(i) for i in DEFAULT_CRF_VALUES[self.compression_combo.currentText()]])


    def browse_watermark(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Select Watermark Image", "", "Image Files (*.png *.jpg *.jpeg)")
        if filename:
            self.watermark_path_edit.setText(filename)
            pixmap = QPixmap(filename)
            if not pixmap.isNull():
                scaled_pixmap = pixmap.scaled(QSize(64, 64), Qt.KeepAspectRatio, Qt.SmoothTransformation) #Scale the pixmap
                self.preview_window.setWatermark(pixmap)

    def show_preview(self):
        video_path = self.drag_drop_frame.dropped_files[0] if self.drag_drop_frame.dropped_files else None
        if not video_path:
            QMessageBox.warning(self, "No Video", "Please drop a video first.")
            return
        self.preview_window.preview_label.watermark_position = self.watermark_position #Set the position to the preview
        self.preview_window.show()

        cap = cv2.VideoCapture(video_path)
        ret, frame = cap.read()
        if ret:
            height, width, channel = frame.shape
            bytesPerLine = 3 * width
            qImg = QImage(frame.data, width, height, bytesPerLine, QImage.Format_BGR888)
            pixmap = QPixmap.fromImage(qImg)
            self.preview_window.setPixmap(pixmap)
            self.preview_window.video_width = width #Store the video width
            self.preview_window.video_height = height #Store the video height
            self.preview_window.show()
        else:
            QMessageBox.warning(self, "Error", "Could not load video frame for preview.")
            return
        cap.release()


    def clear_watermark(self): #Clear function
        self.watermark_path_edit.clear()
        self.preview_window.setWatermark(None)
        self.watermark_position = QPoint(10, 10) #Reset the position
        self.preview_window.preview_label.update() #Force a redraw


###START_COMPRESSOR!!!#####
###START_COMPRESSOR!!!#####
###START_COMPRESSOR!!!#####
###START_COMPRESSOR!!!#####
###START_COMPRESSOR!!!#####
###START_COMPRESSOR!!!#####


    def start_compression(self):
        preset = self.preset_combo.currentText()
        if not self.drag_drop_frame.dropped_files:
            QMessageBox.warning(self, "No Files", "Please drop video files first.")
            return 
        

        self.process_output.clear()  # Clear the QTextEdit HERE!
        if not self.terminal_group.isChecked():
            self.terminal_group.setChecked(True)


        
        crf_value = int(self.compression_number_combo.currentText())
        compression_level = self.compression_combo.currentText()
        video_codec = self.video_codec_map[self.video_codec_combo.currentText()] #Get the real codec name
        watermark_path = self.watermark_path_edit.text()


        self.drag_drop_frame.compressing_icons()
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.show()

        preview_width = self.preview_window.preview_label.width()
        preview_height = self.preview_window.preview_label.height()
        video_width = self.preview_window.video_width
        video_height = self.preview_window.video_height

        x_preview = self.watermark_position.x() #Get the position from the stored position
        y_preview = self.watermark_position.y() #Get the position from the stored position

        x = int(x_preview * (video_width / preview_width))
        y = int(y_preview * (video_height / preview_height))


        self.drag_drop_frame.compress_files(crf_value, compression_level, video_codec, watermark_path, x, y, preset)
        self.watermark_position = QPoint(10, 10) #Reset the position

#######################_SETINGS_TAB_#########################
    ####_SETINGS_TAB_####
    ####_SETINGS_TAB_####
    ####_SETINGS_TAB_####
    

    def setup_settings_tab(self):
        settings_tab_layout = QtWidgets.QVBoxLayout(self.settings_tab)

        # Font Selection
        font_group = QtWidgets.QGroupBox("Font Selection")
        font_layout = QtWidgets.QHBoxLayout(font_group)

        self.font_combo = QtWidgets.QComboBox()
        font_layout.addWidget(self.font_combo)

        # Load custom fonts from directory
        fonts_dir = "Fonts"  # Your fonts directory
        if os.path.exists(fonts_dir):
            for filename in os.listdir(fonts_dir):
                if filename.lower().endswith(('.ttf', '.otf')):  # Check for font files
                    font_path = os.path.join(fonts_dir, filename)
                    font_id = QFontDatabase.addApplicationFont(font_path) #Load the fonts
                    if font_id != -1: #Check if the font was loaded
                        families = QFontDatabase.applicationFontFamilies(font_id) #Get the font families
                        if families:
                            self.font_combo.addItems(families) #Add the font family to the combo box
                    else:
                        print(f"Failed to load font: {font_path}")
        else:
            print(f"Fonts directory not found: {fonts_dir}")

        # Example usage: apply selected font to a label
        self.test_label = QtWidgets.QLabel("Test Text")
        settings_tab_layout.addWidget(self.test_label)

        self.font_combo.currentIndexChanged.connect(self.apply_selected_font)

        settings_tab_layout.addWidget(font_group)
        settings_tab_layout.addStretch(1) # Add stretch to push content to the top

    def apply_selected_font(self):
        selected_font_family = self.font_combo.currentText()
        if selected_font_family:
            font = QtGui.QFont(selected_font_family)
            self.update_all_fonts(font)
            self.test_label.setFont(font)

    def update_all_fonts(self, font):
        # List of widgets you want to update (start with specific ones)
        widgets_to_update = [
            self.title_label,
            self.header_label,
            self.processing_label,
            self.log_status_label,
            self.compress_button,
            self.browse_file_button,
            self.browse_directory_button,
            self.watermark_browse_button,
            self.watermark_clear_button,
            self.show_preview_button,
            # Add other specific widgets here...
        ]

        # Get all children widgets of the main window and add labels and buttons
        all_children = self.findChildren(QtWidgets.QWidget)
        for child in all_children:
            if isinstance(child, (QtWidgets.QLabel, QtWidgets.QPushButton, QtWidgets.QGroupBox, QtWidgets.QCheckBox)): #Check for QCheckBox too
                if child not in widgets_to_update: #Avoid duplicates
                    widgets_to_update.append(child)

        # Update fonts for the widgets
        for widget in widgets_to_update:
            if isinstance(widget, (QtWidgets.QLabel, QtWidgets.QPushButton, QtWidgets.QGroupBox, QtWidgets.QCheckBox)):
                widget.setFont(font)
        #Update the text edit font
        self.process_output.setFont(font)
        #Update the combo box fonts
        self.compression_combo.setFont(font)
        self.compression_number_combo.setFont(font)
        self.video_codec_combo.setFont(font)
        self.preset_combo.setFont(font)
        self.font_combo.setFont(font)
        #Update the line edit font
        self.watermark_path_edit.setFont(font)




###############################################################



    def setup_other_tabs(self, tab, text):
        layout = QVBoxLayout()
        tab.setLayout(layout)
        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)

    def closeEvent(self, event):
        reply = QMessageBox.question(self, 'Quit', 'Do you want to quit?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            event.accept()
        else:
            event.ignore()



if __name__ == "__main__":
    app = QApplication(sys.argv)
    auth_window = AuthWindow(MainWindow)
    if auth_window.run() == QtWidgets.QDialog.Accepted:
        window = MainWindow()
        window.show()
        sys.exit(app.exec_())
    else:
        sys.exit()