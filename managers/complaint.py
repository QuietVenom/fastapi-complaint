import os
import uuid

from constants import TEMP_FILE_FOLDER
from db import database
from services.ses import SESService
from models import RoleType, State, complaint, transaction
from services.s3 import S3Service
from services.wise import WiseService
from utils.helpers import decode_photo

s3 = S3Service()
ses = SESService()
wise = WiseService()


class ComplaintManager:
    @staticmethod
    async def get_complaints(user):
        q = complaint.select()
        if user["role"] == RoleType.complainer:
            q = q.where(complaint.c.complainer_id == user["id"])
        elif user["role"] == RoleType.approver:
            q = q.where(complaint.c.state == State.pending)
        return await database.fetch_all(q)

    @staticmethod
    async def create_complaint(complaint_data, user):
        complaint_data["complainer_id"] = user["id"]
        encoded_photo = complaint_data.pop("encoded_photo")
        extension = complaint_data.pop("extension")
        name = f"{uuid.uuid4()}.{extension}"
        path = os.path.join(TEMP_FILE_FOLDER, name)
        decode_photo(path, encoded_photo)
        complaint_data["photo_url"] = s3.upload(path, name, extension)
        os.remove(path)
        id_ = await database.execute(complaint.insert().values(complaint_data))
        await ComplaintManager.issue_transaction(complaint_data["amount"], f"{user['first_name']} {user['last_name']}", user["iban"], id_)
        return await database.fetch_one(complaint.select().where(complaint.c.id == id_))

    @staticmethod
    async def delete(complaint_id):
        await database.execute(complaint.delete().where(complaint.c.id == complaint_id))

    @staticmethod
    async def approve(complaint_id):
        await database.execute(
            complaint.update()
            .where(complaint.c.id == complaint_id)
            .values(status=State.approved)
        )
        ses.send_mail(
            "Your complaint has been approved", 
            ["izco.marcos@gmail.com"], 
            "Congrats! Your claim is approved, check your bank account in 2 days time."
        )

    @staticmethod
    async def reject(complaint_id):
        await database.execute(
            complaint.update()
            .where(complaint.c.id == complaint_id)
            .values(status=State.rejected)
        )
    
    @staticmethod
    async def issue_transaction(amount, full_name, iban, complaint_id):
        quote_id = wise.create_quote(amount)
        recipient_id = wise.create_recipient_account(full_name, iban)
        transfer_id = wise.create_transfer(recipient_id, quote_id)
        data = {
            "quote_id": quote_id,
            "transfer_id": transfer_id,
            "target_account_id": str(recipient_id),
            "amount": amount,
            "complaint_id": complaint_id,
        }
        await database.execute(transaction.insert().values(**data))
