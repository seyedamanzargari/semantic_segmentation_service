import os
import shutil

import flash
import torch
from flash.image import SemanticSegmentation
from torchmetrics import IoU, F1, Accuracy, Precision, Recall
from utils.augment import Augmentor

from utils import dataloader, logger, utils, datahandler
from glob import glob

data_path = '/home/amir/Projects/rutilea_singularity_gear_inspection/backbone/dataset/coco/images'
labels_path = "/dataset/coco/masks/"
labels_json_path = "/home/amir/Projects/rutilea_singularity_gear_inspection/backbone/dataset/coco/result.json"


class SemanticSegmentTrainer:
    def __init__(self, backbone, head, data_type, pre_trained_path=None, is_augment=False, augment_params=None, label_map=None):
        self.head = head
        self.backbone = backbone
        self.pre_trained_path = pre_trained_path
        self.is_augment = is_augment
        self.augment_params = augment_params
        self.labelmap=label_map
        self.data_type = data_type

    def augment(self, images_path, masks_path, augment_params):

        try:
            os.mkdir('/dataset/temp')
        except FileExistsError:
            shutil.rmtree('/dataset/temp')
            os.mkdir('/dataset/temp')

        os.makedirs('/dataset/temp/images')
        os.makedirs('/dataset/temp/masks')

        for image_path in glob(os.path.join(images_path, '*')):
            shutil.copy(image_path, '/dataset/temp/images')
        for mask_path in glob(os.path.join(masks_path, '*')):
            shutil.copy(mask_path, '/dataset/temp/masks')

        os.makedirs('/dataset/temp/augmented')

        aug = Augmentor('/dataset/temp/images', '/dataset/temp/masks', '/dataset/temp/augmented')
        if augment_params:
            images_path, masks_path = aug.auto_augment(**augment_params)
        else:
            images_path, masks_path = aug.auto_augment()
        return images_path, masks_path

    def train_from_images_mask(self, images_path, masks_path, save_name, batch_size=4, num_dataloader_workers=8, epochs=100,
                               num_classes=2, validation_split=0.2):
        """
        :param images_path: images should be in png format
        :param masks_path: mask path should be raw image and in png format
        :return:
        """
        if self.is_augment:
            images_path, masks_path = self.augment(images_path, masks_path, self.augment_params)

        utils.remove_overuse_image_in_path(images_path, masks_path)
        utils.check_mask_with_cv(images_path, masks_path)

        datamodule = dataloader.get_dataset_for_flash(images_path, masks_path, batch_size,
                                                      num_workers=num_dataloader_workers, num_classes=num_classes,
                                                      validation_split=validation_split)
        # 2. Build the task
        if self.pre_trained_path != None:
            model = SemanticSegmentation.load_from_checkpoint(
                self.pre_trained_path)

        else:
            model = SemanticSegmentation(
                backbone=self.backbone,
                head=self.head,
                num_classes=datamodule.num_classes,
                metrics=[IoU(num_classes=datamodule.num_classes),
                         F1(num_classes=datamodule.num_classes,
                            mdmc_average='samplewise'),
                         Accuracy(num_classes=datamodule.num_classes,
                                  mdmc_average='samplewise'),
                         Precision(num_classes=datamodule.num_classes,
                                   mdmc_average='samplewise'),
                         Recall(num_classes=datamodule.num_classes,
                                mdmc_average='samplewise')],
            )
        # 3. Create the trainer and finetune the model
        trainer = flash.Trainer(
            max_epochs=epochs, logger=logger.ClientLogger(), gpus=torch.cuda.device_count())
        trainer.finetune(model, datamodule=datamodule, strategy="no_freeze")
        trainer.save_checkpoint(os.path.join(os.environ.get(
            'WEIGHTS_DIR', '/weights'), "{}_model.pt".format(save_name)))
        result = trainer.validate(model, datamodule=datamodule)

        return result[0]

    def train(self, images_path, annotation_path, save_name, batch_size=4, num_dataloader_workers=8, epochs=100,
                        num_classes=2,
                        validation_split=0.2):
        """
        :param images_path: jpg or png images path
        :param json_annotation_path: coco dataset annotation path
        :param save_name: save weight name ( you can add time to it)
        :param batch_size: batch size for train
        :param num_dataloader_workers: depends on your cpu
        :param epochs: max number of epochs
        :return: {"result": "staus", "error": "error message"}
        """

        if self.data_type in ["coco", "COCO"]:
            images_path, masks_path = datahandler.coco_data(images_path, annotation_path)
        elif self.data_type in ['pascal', 'pascal_voc', 'pascal-voc']:
            images_path, masks_path, num_classes = datahandler.pascal_voc_data(images_path, annotation_path, self.labelmap)
        else:
            raise ValueError("Data type not supported")

        result = self.train_from_images_mask(images_path, masks_path, save_name, batch_size, num_dataloader_workers,
                                             epochs, num_classes, validation_split)
        return result


if __name__ == '__main__':
    #train_from_coco(data_path, labels_json_path, "coco_train")
    print()
