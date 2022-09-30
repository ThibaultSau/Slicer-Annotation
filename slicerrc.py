# import dicomweb_client
# import vtk, ctk
# import DICOMLib
from genericpath import isfile
import slicer, qt
import os
from DICOMLib import DICOMUtils

import numpy as np
import pickle
import os
from functools import partial
from datetime import datetime

color_dict = {
    "Pastel Red": [255, 160, 160],
    "Pastel Blue": [167, 199, 231],
    "Pastel Green": [193, 225, 193],
    "Pastel Orange": [250, 200, 152],
    "Pastel Pink" : [248, 200, 220],
    "Pastel Purple":[195, 177, 225],
    "Pastel Yellow":[255, 250, 160],
    "Grey" : [192,192,192],
}

# TODO : avoir un bouton pour ouvrir le dossier du patient
# TODO : DOCUMENTATION

# TODO : bug quand réimport une seg, ne peut plus changer de patient
# TODO : fenetre seg qui est au dessus de slicer mais pas au dessus de toute les fenetres 

# TODO : importer toutes les segmentations si elle ont été volumes
# TODO : Gérer les segmentations incomplètes/que les ovaires sains segmentés...

def restart():
    slicer.app.restart()

class InfoDisplay(qt.QGroupBox):
    def __init__(self, title="",blinking=False):
        super().__init__(title)
        self.text_widget = qt.QLabel()
        # self.scroll_area = qt.QScrollArea()
        # self.scroll_area.setWidget(self.text_widget)
        self.custom_layout = qt.QHBoxLayout(self)
        self.custom_layout.addWidget(self.text_widget)
        self.setLayout(self.custom_layout)
        self.blinking = blinking

    def setText(self,text):
        if self.blinking :
            self.blink()            
        self.text_widget.setText(text)

    def set_timer(self,time,function):
        timer = qt.QTimer(self)
        timer.setInterval(time) 
        timer.setSingleShot(True)
        timer.timeout.connect(function)
        timer.start()

    def set_border_red(self):
        self.setStyleSheet("QGroupBox { border: none;padding : 25 5 px;}")

    def reset_border(self):
        self.setStyleSheet("")

    def blink(self):
        self.set_timer(100,self.set_border_red)
        self.set_timer(100+50,self.reset_border)


class DirectoryLineEdit(qt.QWidget, qt.QObject):
    clicked = qt.Signal(str)

    def __init__(self, title="Dossier", button_text="Charger", default_text=None):
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
        self.exported_patients = {}
        self.exported_patients_file='exported_patients.pkl'
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

        self.setWindowTitle("Editeur de segmentation")
        self.custom_layout = qt.QGridLayout()
        self.patient_list = qt.QListWidget()
        self.patient_list.itemDoubleClicked.connect(self.load_from_widget)

        self.dialog_window = InfoDisplay("Informations du patient")
        self.info_window = InfoDisplay("Log d'action",blinking=True)


        self.search_bar.clicked.connect(self.change_current_dir)

        self.export_dir_bar = DirectoryLineEdit(
            "Dossier d'export", "Confirmer", default_text=self.export_dir
        )
        self.export_dir_bar.clicked.connect(self.change_export_dir)

        self.operator_bar = DirectoryLineEdit(
            "Nom de l'opérateur", "Confirmer", default_text=self.operator_name
        )
        self.operator_bar.clicked.connect(self.change_operator_name)

        next_button = qt.QPushButton("Segmentation du patient terminée")
        next_button.clicked.connect(self.next)
        export_button = qt.QPushButton("Exporter les images du patient en nrrd")
        export_button.clicked.connect(self.save_all_volumes)

        listwidgetsize = 30
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
    
    def write_config(self):
        config_path = os.path.join(os.path.normpath(slicer.app.slicerHome),'config_seg.txt')
        with open(config_path,'w') as f:
            f.write(self.current_dir+"\n")
            f.write(self.export_dir+"\n")
            f.write(self.operator_name+"\n")       

    def change_operator_name(self, operator_name):
        print(f"Changing operator name to : {operator_name} ")
        self.operator_name = operator_name
        self.info_window.setText("Changement du nom de l'opérateur")
        self.write_config()

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
            self.exported_patients[self.current_patient] = 2
            self.export_exported_patients()
        else:
            self.indice = 0
        while self.patients[self.indice] in self.exported_patients.keys():
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
            self.info_window.setText("Aucun patient chargé, rien à faire")
        elif self.export_dir is None:
            self.info_window.setText("Pas de dossier d'export")
        else:
            self.info_window.setText("Erreur inconnue pendant l'exportation des volumes du patient")

    # TODO : améliorer cette fonction ? si elle est pas buguée
    def load_exported_patients(self):
        if self.current_dir and self.export_dir:
            export_folder = os.path.join(self.current_dir, self.export_dir)
            exported_patients_file = os.path.join(export_folder,self.exported_patients_file)
            if os.path.isfile(exported_patients_file):
                with open(exported_patients_file,'rb') as f:
                    self.exported_patients = pickle.load(f)

    def export_exported_patients(self):
        if self.current_dir and self.export_dir:
            export_folder = os.path.join(self.current_dir, self.export_dir)
            exported_patients_file = os.path.join(export_folder,self.exported_patients_file)
            with open(exported_patients_file,'wb') as f:
                pickle.dump(self.exported_patients,f)

    def save_all_seg(self, lesion_specificity="lesion"):
        # Getting the current date and time
        dt = datetime.now()
        if self.current_patient and self.export_dir:
            self.info_window.setText(f"{lesion_specificity.replace('_',' ')} segmentation exported")
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
                            + "_"
                            + self.operator_name
                            + "_"
                            + str(dt)[:16].replace(" ", "-").replace(":", "_")
                            + "_"
                            + lesion_specificity
                            + "_"
                            + ".seg.nrrd",
                        )
                        slicer.util.exportNode(
                            seg,
                            seg_name,
                        )
                        print(f"Segmentation {seg_name} saved")
                if self.current_patient not in self.exported_patients.keys():
                    self.exported_patients[self.current_patient] = 1
                    self.export_exported_patients()
            else:
                self.info_window.setText("Rien a exporter")
        elif self.current_patient is None:
            self.info_window.setText("Pas de patient chargé, rien a faire")
        elif self.export_dir is None:
            self.info_window.setText("Pas de dossier d'export")
        else:
            self.info_window.setText("Erreur inconnue pendant l'exportation des volumes du patient")

    def filter_patient_seg(self, patient_exported_image):
        is_seg = "seg.nrrd" in patient_exported_image
        for i in range(4):
            is_seg = is_seg and self.lesion_name[i] in patient_exported_image

    def update_dialog_window(self):
        text = self.current_patient + ":\n"
        if self.patient_info :
            if  self.current_patient in self.patient_info.keys() :
                current_patient_info = self.patient_info[self.current_patient]
                for i, info in enumerate(current_patient_info):
                    text += (
                        f"Lesion {i+1}:  {str(info)}".replace("'", "")
                        .replace("{", "")
                        .replace("}", "")
                    )
                    text += "\n"
            else :
                text += "No patient info found\n"
        text += "\nVolume a segmenter : au choix, un par ligne\n\n"
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
                text += 'Un parmis : '
                text += text_to_add
                text += ".\n"
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
        self.load_patients_in_list()
        current_patient_widget = self.patient_list.item(self.indice)
        current_patient_widget.setBackground(qt.QBrush(qt.QColor(*color_dict["Grey"])))
        self.update_dialog_window()

    def change_export_dir(self, export_dir):
        self.export_dir = export_dir
        if not os.path.isdir(os.path.join(self.current_dir, export_dir)):
            print("patient export dir does not exist, creating")
            os.mkdir(os.path.join(self.current_dir, export_dir))
        if self.export_dir in self.patients:
            self.patients.remove(self.export_dir)
        if self.current_dir:
            self.load_exported_patients()
            self.load_patients_in_list()
        self.info_window.setText("Changement du dossier d'export")
        self.write_config()

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
                            "diagnosis": parts[27].rstrip("\n"),

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
        self.info_window.setText('Dossier chargé')
        self.write_config()

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
            for i in range(nb_lesion):
                button = qt.QPushButton(f"{i+1}")
                button.clicked.connect(partial(self.export, i + 1))
                button_layout.addWidget(button, qt.Qt.AlignVCenter)
            patient_list_layout.addWidget(patient_export_button, qt.Qt.AlignVCenter)
            patient_export_button.setMaximumSize(
                int(1.5 * (patient_export_button.size.width() / 3)),
                patient_export_button.size.height(),
            )

            if patient not in self.exported_patients.keys():
                patient_list_item.setBackground(qt.QBrush(qt.QColor(*color_dict['Pastel Red'])))
            elif self.exported_patients[patient] == 1:
                patient_list_item.setBackground(qt.QBrush(qt.QColor(*color_dict['Pastel Orange'])))
            elif self.exported_patients[patient] == 2:
                patient_list_item.setBackground(qt.QBrush(qt.QColor(*color_dict['Pastel Green'])))
                
            width = patient_widget.sizeHint.width()
            height = patient_widget.sizeHint.height()
            if width > max_width:
                max_width = width
            self.patient_list.setItemWidget(patient_list_item, patient_widget)
            self.patient_list.setMinimumWidth(self.patient_list.sizeHintForColumn(0))
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
