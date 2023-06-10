from fastapi import APIRouter, UploadFile
import numpy as np
import asyncio
import cv2
import base64
import uuid
import os
import torch
from PIL import Image
from torchvision.ops import box_iou


class doraemong:
    def __init__(self):
        self.label_li = np.array(['fat', 'thin'])

        self.model = torch.hub.load(
            'ultralytics/yolov5', 'custom', path='./asset/epoch77-l.pt')
        self.model.names[0] = '최고 도라에몽'
        self.output_folder = './temp_output'

    async def remove_overlapping_boxes(self, boxes, scores, labels, threshold):
        num_boxes = len(boxes)

        # 중첩된 객체 검출을 위한 IoU 계산
        iou = box_iou(boxes, boxes)

        # IoU 값의 임계치를 기준으로 중첩 여부 확인 보편적으로 0.5지만, 라벨링 직접해서 0.8로 설정
        overlapping_boxes = iou > threshold

        # 중첩된 박스를 제거하기 위한 마스크 생성
        mask = torch.ones(num_boxes, dtype=torch.bool)

        for i in range(num_boxes):
            if mask[i]:
                # 중첩된 객체의 인덱스 목록
                overlapping_indices = torch.nonzero(
                    overlapping_boxes[i]).squeeze(1)

                # 중첩된 객체 중 가장 높은 신뢰도를 가진 객체 선택
                max_score_idx = torch.argmax(scores[overlapping_indices])
                max_score_box_idx = overlapping_indices[max_score_idx]

                # 선택한 객체 이외의 중첩된 객체들의 마스크를 False로 설정
                mask[overlapping_indices] = False
                # 선택한 객체의 마스크를 True로 설정
                mask[max_score_box_idx] = True

                # 라벨이 다른 경우에도 중첩 여부 확인하여 처리
                for idx in overlapping_indices:
                    if labels[idx] != labels[max_score_box_idx]:
                        mask[idx] = False
        return mask

    async def process_predictions(self, predictions, threshold):
        boxes = predictions.xyxy[0][:, :4]  # 바운딩박스 좌표
        scores = predictions.xyxy[0][:, 4]  # 신뢰도
        labels = predictions.xyxy[0][:, 5]  # 예측된 라벨

        # 중첩된 박스 제거
        mask = await self.remove_overlapping_boxes(boxes, scores, labels, threshold)
        return mask

    async def imagedown_async(self, img_path):
        image = Image.open(img_path)
        results = self.model(image)

        # mask true인덱스만 추출 -> 중첩 박스 제거
        mask = await self.process_predictions(results, threshold=0.8)
        results.xyxy[0] = results.xyxy[0][torch.nonzero(mask).squeeze(1)]

        # 라벨이 노말인 경우 도라에몽으로 변환
        mask_tmp = results.xyxy[0][:, 5] == 1
        results.xyxy[0][mask_tmp, 4] = (1-results.xyxy[0][mask_tmp, 4])/2

        # 라벨이 노말인 경우 도라에몽으로 변환
        mask_tmp = results.xyxy[0][:, 5] == 0
        results.xyxy[0][mask_tmp, 4] = (results.xyxy[0][mask_tmp, 4]+1)/2

        # 라벨 전체 도라에몽으로
        results.xyxy[0][:, 5] = results.xyxy[0][:, 5]*0

        # 최고 도라에몽만 추출
        try:
            results.xyxy[0] = results.xyxy[0][results.xyxy[0]
                                              [:, 4] == results.xyxy[0][:, 4].max()]
        except RuntimeError:
            pass

        # 결과 이미지 저장
        results.save(save_dir=self.output_folder, exist_ok=True)

        data = None  # data 변수 초기화
        for detection in results.pandas().xyxy[0].iterrows():
            _, data = detection
        try:
            return data['confidence']
        except:
            return 0

    async def predict_batch(self, img_paths):
        results = await asyncio.gather(*(self.imagedown_async(i) for i in img_paths))
        predict_arr = np.max(results)

        recommend = self.label_li[np.argmax(results)]
        return recommend, predict_arr

    async def predict(self, image):
        get_pb = await self.predict_batch(['./temp/'+image])
        recommend = get_pb[0]
        predict_arr = get_pb[1]
        return recommend, predict_arr


route = APIRouter()


@route.post("/photo")
async def upload_photo(file: UploadFile):
    doraecls = doraemong()
    UPLOAD_DIR = "./temp"
    PREDICT_DIR = "./temp_output"
    content = await file.read()
    filename = f"{str(uuid.uuid4())}.jpg"
    with open(os.path.join(UPLOAD_DIR, filename), "wb") as fp:
        fp.write(content)
    json_string = await doraecls.predict(filename)

    os.remove(os.path.join(UPLOAD_DIR, filename))
    img = cv2.imread('E:/WD/Doraemon_fist/temp_output/'+filename)
    jpg_img = cv2.imencode('.jpg', img)
    b64_string = base64.b64encode(jpg_img[1]).decode('utf-8')
    os.remove(os.path.join(PREDICT_DIR, filename))
    if json_string[0] == 'fat':
        result = {"recommend": json_string[0], 'predict_arr': str(
            round(json_string[1]*100, 1)), 'filename': b64_string}
    else:
        result = {"recommend": json_string[0], 'predict_arr': str(
            round((1-json_string[1])*100, 1)), 'filename': b64_string}
    return result
