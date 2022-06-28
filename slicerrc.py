# Python commands in this file are executed on Slicer startup

# Examples:
#
# Load a scene file
# slicer.util.loadScene('c:/Users/SomeUser/Documents/SlicerScenes/SomeScene.mrb')
#
# Open a module (overrides default startup module in application settings / modules)
# slicer.util.mainWindow().moduleSelector().selectModule('SegmentEditor')
#
#import dicomweb_client
#import vtk,  ctk
#import DICOMLib
import qt, slicer
import os 
from DICOMLib import DICOMUtils

# TODO : rajouter timestamp et nom de la personne qui segmente
# TODO : quand le script est relancé recommencer au dernier patient 
# TODO : améliorer la fenetre next : liste des patients, patients faits et previous, cliquer sur un patient le charge
# TODO : Ne pas exporter tout les rasters des patients
# TODO : si une segmentatoin est faite, la charger quand on relance le script

# TODO : Ajouter une fenetre de dialogue pour exporter une sous segmentation dans le cas ou il y a plusieurs lesions pour une patiente
# TODO : Ajouter une option pour exporter un ovaire sain
# TODO : ajouter comme info : le coté, la taille, le diagnostic final.
# TODO : faire une grosse fenetre qui rassemble toutes les informations et facon d'intéragir
# TODO : Faire en sorte que la fenetre soit toujours en premier plan

class PatientSegManager:
    #TODO: bug si
    def __init__(self, patient_directory,name='',export_dir='export'):
        self.patient_basedir = patient_directory
        self.export_dir = export_dir
        self.indice=0
        self.all_patient=os.listdir(self.patient_basedir)
        self.name=name

        if self.export_dir in self.all_patient:
            self.all_patient.remove(self.export_dir)

        self.patient_status={k:0 for k in self.all_patient}
        self.export_path = os.path.join(self.patient_basedir,self.export_dir)

        if not os.path.isdir(self.export_path):
          os.mkdir(self.export_path)

        while self.patient_status[self.all_patient[self.indice]]!=0:
            self.indice += 1

        self.patient_widget = qt.QListWidget()
        self.patient_widget.itemDoubleClicked.connect(self.loadFromWidget)
        self.startup()
        patient_path = os.path.join(self.patient_basedir,self.all_patient[self.indice])
        #self.load(patient_path)

    def startup(self):
        patients_segmented = os.listdir(self.export_path)
        if patients_segmented :
            for patient in patients_segmented :
                self.patient_status[patient] = 1
        for patient in self.all_patient:
            widget = qt.QListWidgetItem(patient, self.patient_widget)
            if self.patient_status[patient] == 1:
                widget.setBackground(qt.Qt.blue)
            elif self.patient_status[patient] == 0:
                widget.setBackground(qt.Qt.red)
            widget.font().setPointSize(25)
        self.patient_widget.show()

    def loadFromWidget(self,item):
        self.indice = self.all_patient.index(item.text())
        patient_path = os.path.join(self.patient_basedir,self.all_patient[self.indice])
        self.load(patient_path)

    def sort_volumes_by_shape(self):
        vol_shape={}
        for node in slicer.util.getNodesByClass('vtkMRMLScalarVolumeNode'):
            shape=slicer.util.arrayFromVolume(node).shape 
            if shape in vol_shape.keys():
                vol_shape[shape].append(node)
            else :
                vol_shape[shape] = [node,]
        return vol_shape

    def save_all_volumes(self, patient_path):
        for volume in slicer.util.getNodesByClass('vtkMRMLScalarVolumeNode'):
            slicer.util.exportNode(volume, os.path.join(patient_path,volume.GetName()[3:].replace(':','')+'.nrrd'))
            print(f'Volume {os.path.join(patient_path,volume.GetName()[3:])} saved')

    def save_all_seg(self, patient_path):
        if slicer.util.getNodesByClass('vtkMRMLSegmentationNode') :
            if not os.path.isdir(patient_path):
                print('patient export dir does not exist, creating')
                os.mkdir(patient_path)
            vol_shape = self.sort_volumes_by_shape()
            for seg in slicer.util.getNodesByClass('vtkMRMLSegmentationNode'):
                master = seg.GetNodeReference(slicer.vtkMRMLSegmentationNode.GetReferenceImageGeometryReferenceRole())
                for item in vol_shape[slicer.util.arrayFromVolume(master).shape]:
                    slicer.util.exportNode(seg, os.path.join(patient_path,item.GetName()[3:].replace(':','')+'_seg.nrrd'))
                    print(f'Segmentation {os.path.join(patient_path,item.GetName()[3:])} saved')
        else:
            print('Nothing to export')

    def load(self, patient_path):
        print(f'Loading patient : {patient_path}')
        loadedNodeIDs = []  # this list will contain the list of all loaded node IDs
        DICOMUtils.openTemporaryDatabase()
        DICOMUtils.importDicom(patient_path, slicer.dicomDatabase)
        patientUIDs = slicer.dicomDatabase.patients()
        print('Loading nodes')
        for patientUID in patientUIDs:
            loadedNodeIDs.extend(DICOMUtils.loadPatientByUID(patientUID))
        print('Volumes loaded :')
        for node in slicer.util.getNodesByClass('vtkMRMLScalarVolumeNode'):
            print(node.GetName())
        print('Volumes to segment : one of')
        vol_shape = self.sort_volumes_by_shape()
        for _, item in vol_shape.items():
            print([patient.GetName() for patient in item])
        print(f'{patient_path} : Loaded')
        current_patient_widget = self.patient_widget.item(self.indice)
        current_patient_widget.setBackground(qt.Qt.lightGray)
        return vol_shape

    def next(self):
        patient_save_path = os.path.join(self.export_path,self.all_patient[self.indice])
        print(f'exporting patient {os.path.join(self.patient_basedir,self.all_patient[self.indice])}')
        if slicer.util.getNodesByClass('vtkMRMLSegmentationNode') is not None:
            print('exporting patient segmentation')
            self.save_all_seg(patient_save_path)
        DICOMUtils.clearDatabase(slicer.dicomDatabase)
        slicer.mrmlScene.Clear()
        self.indice += 1
        while self.patient_status[self.all_patient[self.indice]]!=0:
            self.indice += 1
        patient_path = os.path.join(self.patient_basedir,self.all_patient[self.indice])
        self.load(patient_path)

class MainWindow(qt.QWidget):
    def __init__(self):
        super().__init__(self)
        self.setWindowTitle("Segmentation editor")
        layout =qt.QGridLayout()

        listWidget = qt.QListWidget()
        patients = os.listdir(r'C:\Users\tib\Desktop\CBIR1-10 - vri')
        for patient in patients:
            qt.QListWidgetItem(patient, listWidget)
    
        layout.addWidget(listWidget,0,0,9)
        layout.addWidget(qt.QPushButton(),0,1,1,1)
        layout.addWidget(qt.QPushButton("Right-Most"),1,1,1,1)
        # Set the layout on the application's window
        self.setLayout(layout)


test = MainWindow()
test.show()


if __name__ == "__main__":
    test = PatientSegManager(r'C:\Users\tib\Desktop\CBIR1-10 - vri',9)

    b=qt.QPushButton('Next Patient')
    b.connect('clicked()',test.next)
    b.styleSheet = "font-size: 24pt; color: aqua; margin: 20px"
    b.show()