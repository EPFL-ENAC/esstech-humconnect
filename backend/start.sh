if [ -n "$SSH_PRIVATE_KEY" ]; then
	mkdir -p /root/.ssh
	chmod 700 /root/.ssh
	echo "$SSH_PRIVATE_KEY" > /root/.ssh/id_ed25519
	chmod 600 /root/.ssh/id_ed25519
	unset SSH_PRIVATE_KEY
fi

uvicorn --host=0.0.0.0 --timeout-keep-alive=0 api.main:app --reload
