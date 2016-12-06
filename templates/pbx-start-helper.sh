#!/bin/bash
#
# To be run by pbx@.service in ExecStartPost
CONFIG_FILE=/media/state/fusionpbx-data/nginx/sites-available/fusionpbx
CONFIG_STAMP=/media/state/fusionpbx-data/.config-installed
SETUP_STAMP=/media/state/fusionpbx-data/.pass

# Wait until config has been copied the first time
while [ ! -f $SETUP_STAMP ]; do
    sleep 1
done

# Check for the web root hack
if [ ! -d $WEB_ROOT/pbx ]; then
    echo "Hacking FusionPBX web root to live under /pbx"
    mv $WEB_ROOT $WEB_ROOT-
    mkdir $WEB_ROOT
    mv $WEB_ROOT- $WEB_ROOT/pbx
fi

# This only needs to be run once after a new config is copied over
if [ -f $CONFIG_STAMP -a $CONFIG_STAMP -nt $0 ]; then
    echo "FusionPBX nginx config already updated; nothing to do"
    exit 0
fi



# Copy the updated nginx config into place
echo "Installing FusionPBX nginx config"
cat > $CONFIG_FILE <<EOF
server {
        listen 80;
        server_name fusionpbx;

        #REST api
        if (\$uri ~* ^.*/api/.*\$) {
                rewrite ^(.*)/api/(.*)\$ \$1/api/index.php?rewrite_uri=\$2 last;
                break;
        }

        #mitel
        rewrite "^.*/provision/MN_([A-Fa-f0-9]{12})\.cfg" /pbx/app/provision/index.php?mac=\$1&file=MN_%7b%24mac%7d.cfg last;
        rewrite "^.*/provision/MN_Generic.cfg" /pbx/app/provision/index.php?mac=08000f000000&file=MN_Generic.cfg last;

        #grandstream
        rewrite "^.*/provision/cfg([A-Fa-f0-9]{12})(\.(xml|cfg))?\$" /pbx/app/provision/?mac=\$1;

        #aastra
        rewrite "^.*/provision/aastra.cfg\$" /pbx/app/provision/?mac=\$1&file=aastra.cfg;
        #rewrite "^.*/provision/([A-Fa-f0-9]{12})(\.(cfg))?\$" /pbx/app/provision/?mac=\$1 last;

        #yealink common
        rewrite "^.*/provision/(y[0-9]{12})(\.cfg)?\$" /pbx/app/provision/index.php?file=\$1.cfg;

        #yealink mac
        rewrite "^.*/provision/([A-Fa-f0-9]{12})(\.(xml|cfg))?\$" /pbx/app/provision/index.php?mac=\$1 last;

        #polycom
        rewrite "^.*/provision/000000000000.cfg\$" "/pbx/app/provision/?mac=\$1&file={%24mac}.cfg";
        #rewrite "^.*/provision/sip_330(\.(ld))\$" /pbx/includes/firmware/sip_330.\$2;
        rewrite "^.*/provision/features.cfg\$" /pbx/app/provision/?mac=\$1&file=features.cfg;
        rewrite "^.*/provision/([A-Fa-f0-9]{12})-sip.cfg\$" /pbx/app/provision/?mac=\$1&file=sip.cfg;
        rewrite "^.*/provision/([A-Fa-f0-9]{12})-phone.cfg\$" /pbx/app/provision/?mac=\$1;
        rewrite "^.*/provision/([A-Fa-f0-9]{12})-registration.cfg\$" "/pbx/app/provision/?mac=\$1&file={%24mac}-registration.cfg";
        rewrite "^.*/provision/([A-Fa-f0-9]{12})-directory.xml\$" "/pbx/app/provision/?mac=\$1&file={%24mac}-directory.xml";

        #cisco
        rewrite "^.*/provision/file/(.*\.(xml|cfg))" /pbx/app/provision/?file=\$1 last;

        #Escene
        rewrite "^.*/provision/([0-9]{1,11})_Extern.xml\$"       "/pbx/app/provision/?ext=\$1&file={%24mac}_extern.xml" last;
        rewrite "^.*/provision/([0-9]{1,11})_Phonebook.xml\$"    "/pbx/app/provision/?ext=\$1&file={%24mac}_phonebook.xml" last;

        access_log /var/log/nginx/access.log;
        error_log /var/log/nginx/error.log;

        client_max_body_size 80M;
        client_body_buffer_size 128k;

        rewrite "^/pbx\$" "/pbx/core/user_settings/user_dashboard.php";
        rewrite "^/pbx/\$" "/pbx/core/user_settings/user_dashboard.php";
        location /pbx/ {
                root /var/www/fusionpbx;
                index index.php;
        }

        location ~ \.php\$ {
                fastcgi_pass unix:/var/run/php5-fpm.sock;
                #fastcgi_pass 127.0.0.1:9000;
                fastcgi_index index.php;
                include fastcgi_params;
                fastcgi_param   SCRIPT_FILENAME /var/www/fusionpbx\$fastcgi_script_name;
        }

        # Disable viewing .htaccess & .htpassword & .db
        location ~ .htaccess {
                deny all;
        }
        location ~ .htpassword {
                deny all;
        }
        location ~^.+.(db)\$ {
                deny all;
        }
}
EOF

# Reload nginx config in container
if test "$(docker ps --filter name=pbx -q | wc -l)" != 0; then
    echo "Reloading nginx configuration"
    docker exec pbx nginx -s reload
fi

# Signal that this doesn't need to be run again
echo "Finished installing FusionPBX nginx configuration"
touch $CONFIG_STAMP
