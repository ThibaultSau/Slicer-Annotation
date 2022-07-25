# import dicomweb_client
# import vtk,  ctk
# import DICOMLib
from genericpath import isfile
import slicer, qt
import os
from DICOMLib import DICOMUtils

import numpy as np
import os
from functools import partial
from PythonQt import QtCore
from datetime import datetime

color_dict = {
    "Pastel Red": [255, 160, 160],
    "Pastel Blue": [167, 199, 231],
    "Pastel Green": [193, 225, 193],
    "Pastel Orange": [250, 200, 152],
    "Pastel Pink" : [248, 200, 220],
    "Pastel Purple":[195, 177, 225],
    "Pastel Yellow":[255, 250, 160],
}

# TODO : option pour exporter en niftii/nrrd, faire deux dossiers, faire deux boutons
# TODO : importer toutes les segmentations si elle ont été volumes
# TODO : Gérer les segmentations incomplètes/que les ovaires sains segmentés...

class InfoDisplay(qt.QGroupBox):
    def __init__(self, title=""):
        super().__init__(title)
        self.text_widget = qt.QLabel("Loaded patient info")
        # self.scroll_area = qt.QScrollArea()
        # self.scroll_area.setWidget(self.text_widget)
        self.custom_layout = qt.QHBoxLayout(self)
        self.custom_layout.addWidget(self.text_widget)
        self.setLayout(self.custom_layout)
    
    def setText(self,text):
        self.text_widget.settext(text)


class DirectoryLineEdit(qt.QWidget, qt.QObject):
    clicked = qt.Signal(str)

    def __init__(self, title="Directory", button_text="Load", default_text=None):
        super().__init__()
        search_bar_layout = qt.QHBoxLayout(self)
        self.label = qt.QLabel(title)
        self.text_input = qt.QLineEdit()
        if default_text:
            self.text_input.setText(default_text)
        self.button = qt.QPushButton(button_text)

        search_bar_layout.addWidget(self.label)
        search_bar_layout.addWidget(self.text_input)
        search_bar_layout.addWidget(self.button)

        self.button.clicked.connect(self.get_text)

    def get_text(self):
        self.clicked.emit(self.text_input.text)


class MainWindow(qt.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(qt.Qt.WindowStaysOnTopHint)
        self.patients = None
        self.exported_patients = None
        self.current_dir = None
        self.current_patient = None
        self.indice = None
        self.lesion_name = {
            0: "sane_ovary",
            1: "lesion_1",
            2: "lesion_2",
            3: "lesion_3",
        }
        self.patient_info = {}

        work_dir,export_dir,operator_name = self.load_config()
        if work_dir is not None :
            self.search_bar = DirectoryLineEdit(
                default_text=work_dir
            )
            self.export_dir = export_dir
            self.operator_name = operator_name
        else :
            self.search_bar = DirectoryLineEdit(
                default_text=r"Enter work directory path"
            )
            self.export_dir = "export"
            self.operator_name = "Pierre"

        self.setWindowTitle("Segmentation editor")
        self.custom_layout = qt.QGridLayout()
        self.patient_list = qt.QListWidget()
        self.patient_list.itemDoubleClicked.connect(self.load_from_widget)

        self.dialog_window = InfoDisplay("Patient Information")
        self.info_window = InfoDisplay("Actions log")


        self.search_bar.clicked.connect(self.change_current_dir)

        self.export_dir_bar = DirectoryLineEdit(
            "Export directory", "Confirm", default_text=self.export_dir
        )
        self.export_dir_bar.clicked.connect(self.change_export_dir)

        self.operator_bar = DirectoryLineEdit(
            "Operator name", "Confirm", default_text=self.operator_name
        )
        self.operator_bar.clicked.connect(self.change_operator_name)

        next_button = qt.QPushButton("Next Patient")
        next_button.clicked.connect(self.next)
        export_button = qt.QPushButton("Export patient image")
        export_button.clicked.connect(self.save_all_volumes)

        listwidgetsize = 20
        self.custom_layout.addWidget(
            self.patient_list, 0, 0, 51, listwidgetsize, qt.Qt.AlignLeft
        )
        self.custom_layout.addWidget(
            next_button, 0, listwidgetsize + 1, qt.Qt.AlignVCenter
        )
        self.custom_layout.addWidget(
            export_button, 1, listwidgetsize + 1, qt.Qt.AlignVCenter
        )
        self.custom_layout.addWidget(self.search_bar, 2, listwidgetsize + 1)
        self.custom_layout.addWidget(self.export_dir_bar, 3, listwidgetsize + 1)
        self.custom_layout.addWidget(self.operator_bar, 4, listwidgetsize + 1)
        self.custom_layout.addWidget(self.dialog_window, 5, listwidgetsize + 1)
        self.custom_layout.addWidget(self.info_window, 9, listwidgetsize + 1)

        # Set the layout on the application's window
        self.setLayout(self.custom_layout)
    
    def load_config(self):
        work_dir,export_dir,operator_name = None, None, None
        config_path = os.path.join(os.path.normpath(slicer.app.slicerHome),'config_seg.txt')
        if os.path.isfile(config_path):
            with open(config_path,'r') as f:
                work_dir = f.readline().rstrip("\n")
                export_dir = f.readline().rstrip("\n")
                operator_name = f.readline().rstrip("\n")
        return work_dir,export_dir,operator_name

    def change_operator_name(self, operator_name):
        print(f"Changing operator name to : {operator_name} ")
        self.operator_name = operator_name

    def sort_volumes_by_shape(self):
        vol_shape = {}
        for node in slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode"):
            shape = slicer.util.arrayFromVolume(node).shape
            if shape in vol_shape.keys():
                vol_shape[shape].append(node)
            else:
                vol_shape[shape] = [
                    node,
                ]
        return vol_shape

    def export_path(self):
        return os.path.join(self.current_dir, self.export_dir, self.current_patient)

    def load_from_widget(self, item):
        print("Loading patient from widget")
        if (
            slicer.util.getNodesByClass(
                "vtkMRMLSegmentationNode"
            )  # Verifier pour le not si ca exporte bien
            and self.current_patient
        ):
            print("Exporting current patient segmentation")
            print(slicer.util.getNodesByClass("vtkMRMLSegmentationNode"))
            self.save_all_seg()
        self.current_patient = item.text()
        self.indice = self.patients.index(item.text())
        DICOMUtils.clearDatabase(slicer.dicomDatabase)
        slicer.mrmlScene.Clear()
        self.load(os.path.join(self.current_dir, self.current_patient))

    def next(self):
        print("Loading Next Patient")
        if self.indice is not None:
            if self.export_dir and self.current_patient:
                if (
                    slicer.util.getNodesByClass("vtkMRMLSegmentationNode")
                    and self.current_patient
                ):
                    print("Exporting current patient segmentation")
                    self.save_all_seg()
            DICOMUtils.clearDatabase(slicer.dicomDatabase)
            slicer.mrmlScene.Clear()
            self.indice += 1
        else:
            self.indice = 0
        while self.patients[self.indice] in self.exported_patients:
            self.indice += 1
        self.current_patient = self.patients[self.indice]
        patient_path = os.path.join(self.current_dir, self.current_patient)
        self.load(patient_path)

    def save_all_volumes(self):
        if self.current_patient and self.export_dir:
            for volume in slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode"):
                slicer.util.exportNode(
                    volume,
                    os.path.join(
                        self.export_path(),
                        volume.GetName()[3:].replace(":", "") + ".nrrd",
                    ),
                )
                print(
                    f"Volume {os.path.join(self.export_path(),volume.GetName()[3:])} saved"
                )
        elif self.current_patient is None:
            print("no patient loaded, nothing to do to save patient volumes")
        elif self.export_dir is None:
            print("No export directory")
        else:
            print("unknown error")

    # TODO : améliorer cette fonction ? si elle est pas buguée
    def update_exported_patients(self):
        if self.current_dir and self.export_dir:
            export_folder = os.path.join(self.current_dir, self.export_dir)
            self.exported_patients = list(
                filter(
                    lambda x: os.listdir(os.path.join(export_folder, x)),
                    os.listdir(export_folder),
                )
            )

    def save_all_seg(self, lesion_specificity=""):
        # Getting the current date and time
        dt = datetime.now()
        if self.current_patient and self.export_dir:
            if slicer.util.getNodesByClass("vtkMRMLSegmentationNode"):
                if not os.path.isdir(self.export_path()):
                    print("patient export dir does not exist, creating")
                    os.mkdir(self.export_path())
                vol_shape = self.sort_volumes_by_shape()
                for seg in slicer.util.getNodesByClass("vtkMRMLSegmentationNode"):
                    master = seg.GetNodeReference(
                        slicer.vtkMRMLSegmentationNode.GetReferenceImageGeometryReferenceRole()
                    )
                    for item in vol_shape[slicer.util.arrayFromVolume(master).shape]:
                        # seg.setMasterVolumeNode(item) utiliser plutot SetNodeReferenceID mais pas de doc pour l'instant
                        seg_name = os.path.join(
                            self.export_path(),
                            item.GetName()[3:].replace(":", "")
                            + self.operator_name
                            + str(dt)[:16].replace(" ", "-").replace(":", "_")
                            + lesion_specificity
                            + ".seg.nrrd",
                        )
                        slicer.util.exportNode(
                            seg,
                            seg_name,
                        )
                        print(f"Segmentation {seg_name} saved")
                self.update_exported_patients()
            else:
                print("Nothing to export")
        elif self.current_patient is None:
            print("no patient loaded, nothing to do to save patient segmentation")
        elif self.export_dir is None:
            print("No export directory")
        else:
            print("unknown error")

    def filter_patient_seg(self, patient_exported_image):
        is_seg = "seg.nrrd" in patient_exported_image
        for i in range(4):
            is_seg = is_seg and self.lesion_name[i] in patient_exported_image

    def update_dialog_window(self):
        text = self.current_patient + ":\n"
        if self.patient_info :
            current_patient_info = self.patient_info[self.current_patient]
            for i, info in enumerate(current_patient_info):
                text += (
                    f"Lesion {i+1}:  {str(info)}".replace("'", "")
                    .replace("{", "")
                    .replace("}", "")
                )
                text += "\n"

        text += "\nVolumes to segment : one of\n\n"
        vol_shape = self.sort_volumes_by_shape()
        for _, item in vol_shape.items():
            text_to_add = [
                patient.GetName() if "Loc" not in patient.GetName() else ""
                for patient in item
            ]
            text_to_add = list(filter(lambda x: x != "", text_to_add))
            if len(text_to_add) > 5:
                text_to_add = [
                    patient_text[: int(len(patient_text) / 2)] + "..."
                    for patient_text in text_to_add
                ]
            text_to_add = (
                str(text_to_add)
                .replace("'", "")
                .replace("imageOrientation", "")
                .replace("[", "")
                .replace("]", "")
            )
            print(text_to_add)
            if len(text_to_add) > 10:
                text += text_to_add
                text += "\n"
        self.dialog_window.setText(text)

    def load(self, patient_path):
        print(f"Loading patient {patient_path} ")
        loadedNodeIDs = []  # this list will contain the list of all loaded node IDs
        DICOMUtils.openTemporaryDatabase()
        DICOMUtils.importDicom(patient_path, slicer.dicomDatabase)
        patientUIDs = slicer.dicomDatabase.patients()
        print("Loading nodes")
        for patientUID in patientUIDs:
            loadedNodeIDs.extend(DICOMUtils.loadPatientByUID(patientUID))
        print("Volumes loaded :")
        for node in slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode"):
            print(node.GetName())

        print(f"{patient_path} : Loaded")
        if self.exported_patients:
            for patient in self.patients:
                patient_widget = self.patient_list.item(self.patients.index(patient))
                if patient in self.exported_patients:
                    patient_widget.setBackground(qt.QBrush(qt.QColor(*color_dict['Pastel Blue'])))
                else:
                    patient_widget.setBackground(qt.QBrush(qt.QColor(*color_dict['Pastel Red'])))
            patient_exported_images = os.path.join(
                self.current_dir, self.export_dir, self.current_patient
            )
            if os.path.isdir(patient_exported_images):
                print("Loading previous segmentations")
                for seg in filter(
                    self.filter_patient_seg, os.listdir(patient_exported_images)
                ):
                    slicer.util.loadSegmentation(
                        os.path.join(patient_exported_images, seg)
                    )
        current_patient_widget = self.patient_list.item(self.indice)
        current_patient_widget.setBackground(qt.Qt.lightGray)
        self.load_patients_in_list()
        self.update_dialog_window()

    def change_export_dir(self, export_dir):
        self.export_dir = export_dir
        if not os.path.isdir(os.path.join(self.current_dir, export_dir)):
            print("patient export dir does not exist, creating")
            os.mkdir(os.path.join(self.current_dir, export_dir))
        if self.export_dir in self.patients:
            self.patients.remove(self.export_dir)
        if self.current_dir:
            self.update_exported_patients()
            if self.current_dir is not None:
                self.load_patients_in_list()

    def parse_info_file(self, info_file_path):
        self.patient_info = {}

        with open(info_file_path, "r") as f:
            f.readline()
            for line in f.readlines():
                parts = line.split(",")
                if parts[0] not in self.patient_info.keys():
                    self.patient_info[parts[0]] = []
                if parts[1] != 0:
                    self.patient_info[parts[0]].append(
                        {
                            "lesion size": parts[2],
                            "lesion_side": parts[3],
                            "diagnosis": parts[4].rstrip("\n"),
                        }
                    )

    def change_current_dir(self, directory):
        info_file = list(
            filter(
                lambda x: os.path.isfile(os.path.join(directory, x)) and ".csv" in x,
                os.listdir(directory),
            )
        )
        if info_file:
            self.parse_info_file(os.path.join(directory, info_file[0]))
        self.patient_list.clear()
        self.current_dir = directory
        self.patients = list(
            filter(
                lambda x: os.path.isdir(os.path.join(directory, x)),
                os.listdir(directory),
            )
        )
        self.change_export_dir(self.export_dir_bar.text_input.text)
        self.info_window.setText()

    def load_patients_in_list(self):
        max_width = 0
        height = None
        nb_lesion = 0
        self.patient_list.clear()
        if self.export_dir and self.export_dir in self.patients:
            self.patients.remove(self.export_dir)
        for patient in self.patients:
            try:
                nb_lesion = len(self.patient_info[patient])
            except:
                nb_lesion = 0
            patient_list_item = qt.QListWidgetItem()
            self.patient_list.addItem(patient_list_item)
            patient_list_item.setText(patient)

            patient_widget = qt.QWidget()
            patient_list_layout = qt.QHBoxLayout(patient_widget)
            patient_list_layout.setContentsMargins(0, 0, 0, 0)
            patient_list_layout.addStretch()

            patient_name = qt.QLabel("".join([" "] * (2 * len(patient) + 5)))
            patient_list_layout.addWidget(patient_name, qt.Qt.AlignLeft)

            patient_export_button = qt.QWidget()
            button_layout = qt.QHBoxLayout(patient_export_button)
            button_layout.setContentsMargins(0, 0, 0, 0)
            button_layout.addStretch()

            if nb_lesion < 2:
                button = qt.QPushButton("ovaire sain")
            else:
                button = qt.QPushButton("sain")
            button.clicked.connect(partial(self.export, 0))
            button_layout.addWidget(button, qt.Qt.AlignVCenter)
            if nb_lesion > 1:
                for i in range(nb_lesion):
                    button = qt.QPushButton(f"{i+1}")
                    button.clicked.connect(partial(self.export, i + 1))
                    button_layout.addWidget(button, qt.Qt.AlignVCenter)
            patient_list_layout.addWidget(patient_export_button, qt.Qt.AlignVCenter)
            patient_export_button.setMaximumSize(
                int(1.5 * (patient_export_button.size.width() / 3)),
                patient_export_button.size.height(),
            )

            if self.exported_patients is not None:
                if patient in self.exported_patients:
                    patient_list_item.setBackground(qt.QBrush(qt.QColor(*color_dict['Pastel Blue'])))#
                else:
                    patient_list_item.setBackground(qt.QBrush(qt.QColor(*color_dict['Pastel Red'])))
            width = patient_widget.sizeHint.width()
            height = patient_widget.sizeHint.height()
            if width > max_width:
                max_width = width
            self.patient_list.setItemWidget(patient_list_item, patient_widget)

        # self.patient_list.setSizePolicy(qt.QtWidgets.QSizePolicy.Expanding)

        self.patient_list.setGridSize(qt.QSize(int(2 * (max_width / 3)), height))

    def export(self, lesion_number, item):
        if slicer.util.getNodesByClass("vtkMRMLSegmentationNode"):
            self.save_all_seg(self.lesion_name[lesion_number])
            for seg in slicer.util.getNodesByClass("vtkMRMLSegmentationNode"):
                slicer.mrmlScene.RemoveNode(seg)


if __name__ == "__main__":
    window = MainWindow()

    window.show()
